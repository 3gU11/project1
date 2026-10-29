"""修复「合同已取消但经销商订单仍卡在已转合同/已通过等状态」的历史数据。

背景：V8 合同管理页「取消合同」与 Go 标记现货触发的 contract-cancel-sync 历史
上只清理 factory_plan / units / 队列，没有联动 dealer_orders，也没有写云端回传
事件，导致订货小程序仍显示「已转合同」。

本脚本默认 dry-run 只打印报告；确认后加 --apply 才写库，并写入
cloud_sync_outbox 的 dealer_order_cancelled 回传事件（幂等，可重复执行）。

判定：订单行 status ∈ {pending, approved, contracted, partial_allocated, allocated}
且 contract_no 非空，且其引用的每个合同在 factory_plan 中都存在且状态为「已取消」。
合同查不到、或仍有未取消合同 → 跳过并在报告中列出原因。

示例：
  .\\.venv\\Scripts\\python.exe tools\\repair_dealer_orders_for_cancelled_contracts.py
  .\\.venv\\Scripts\\python.exe tools\\repair_dealer_orders_for_cancelled_contracts.py --order-no DO1792753221620262851
  .\\.venv\\Scripts\\python.exe tools\\repair_dealer_orders_for_cancelled_contracts.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crud.dealer_orders import (  # noqa: E402
    CANCELLABLE_DEALER_ORDER_STATUSES,
    CANCELLED_CONTRACT_STATUS,
    cancel_dealer_orders_for_contracts,
    load_factory_plan_contract_statuses,
    split_contract_nos,
)
from database import get_engine  # noqa: E402


def plan_repairs(conn, order_no: str = "") -> dict[str, Any]:
    """只读扫描，返回待修复行（targets）与跳过行（skipped）。"""
    order_no = str(order_no or "").strip()
    params: dict[str, Any] = {"cancellable_statuses": tuple(CANCELLABLE_DEALER_ORDER_STATUSES)}
    where = [
        "COALESCE(TRIM(contract_no), '') <> ''",
        "status IN :cancellable_statuses",
    ]
    if order_no:
        where.append("order_no = :order_no")
        params["order_no"] = order_no
    rows = conn.execute(
        text(
            "SELECT id, order_no, line_no, contract_no, status "
            "FROM dealer_orders "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY order_no, line_no, id"
        ).bindparams(bindparam("cancellable_statuses", expanding=True)),
        params,
    ).mappings().all()

    all_contract_ids = sorted({cid for row in rows for cid in split_contract_nos(row["contract_no"])})
    # 与 cancel_dealer_orders_for_contracts 使用同一份合同状态判定，保证 dry-run 与实际取消一致。
    contract_statuses = load_factory_plan_contract_statuses(conn, all_contract_ids)

    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        contract_nos = split_contract_nos(row["contract_no"])
        base = {
            "id": int(row["id"]),
            "order_no": str(row["order_no"] or "").strip(),
            "line_no": row["line_no"],
            "status": str(row["status"] or "").strip(),
            "contract_no": str(row["contract_no"] or "").strip(),
        }
        missing = [cid for cid in contract_nos if cid not in contract_statuses]
        # 同一合同在 factory_plan 里可能有多行（每机型一行），要求每一行都已是「已取消」。
        not_cancelled = [
            cid
            for cid in contract_nos
            if cid in contract_statuses and contract_statuses[cid] != {CANCELLED_CONTRACT_STATUS}
        ]
        if missing or not_cancelled:
            skipped.append({**base, "missing_contracts": missing, "not_cancelled_contracts": not_cancelled})
            continue
        targets.append(base)

    return {
        "targets": targets,
        "skipped": skipped,
        "orders": sorted({target["order_no"] for target in targets}),
        "contract_nos": all_contract_ids,
    }


def apply_repairs(
    conn,
    plan: dict[str, Any],
    operator: str = "system",
    reason: str = "",
) -> dict[str, Any]:
    """在调用方事务里取消计划中的订单行并入队回传事件。"""
    target_ids = [int(target["id"]) for target in plan.get("targets") or []]
    if not target_ids:
        return {"orders": [], "lines": 0, "events": []}
    contract_ids = sorted(
        {cid for target in plan["targets"] for cid in split_contract_nos(target["contract_no"])}
    )
    return cancel_dealer_orders_for_contracts(
        conn,
        contract_ids,
        operator=operator,
        reason=reason,
        line_ids=target_ids,
    )


def _print_plan(plan: dict[str, Any], apply: bool) -> None:
    mode = "apply" if apply else "dry-run"
    print(
        f"[{mode}] 待取消订单行 {len(plan['targets'])} 行 / {len(plan['orders'])} 单；"
        f"跳过 {len(plan['skipped'])} 行"
    )
    for target in plan["targets"]:
        print(
            f"  TARGET order={target['order_no']} line={target['line_no']} "
            f"status={target['status']} contracts={target['contract_no']}"
        )
    for item in plan["skipped"]:
        print(
            f"  SKIP   order={item['order_no']} line={item['line_no']} status={item['status']} "
            f"contracts={item['contract_no']} missing={item['missing_contracts']} "
            f"not_cancelled={item['not_cancelled_contracts']}"
        )


def _configure_stdout() -> None:
    """Windows 控制台在管道下默认不是 UTF-8，统一输出编码避免中文报告乱码。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (TypeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="修复合同已取消但经销商订单未取消的历史数据")
    parser.add_argument("--apply", action="store_true", help="确认写库；默认仅 dry-run 打印报告")
    parser.add_argument("--order-no", default="", help="只处理指定经销商订单号")
    parser.add_argument("--operator", default="system", help="操作人（写入 reviewed_by 与回传事件）")
    args = parser.parse_args(argv)
    reason = f"历史数据修复：关联合同已取消（操作人 {args.operator}）"

    with get_engine().connect() as conn:
        plan = plan_repairs(conn, args.order_no)
    _print_plan(plan, bool(args.apply))

    if not args.apply:
        print("dry-run 未写库；确认无误后加 --apply 执行。")
        return 0
    if not plan["targets"]:
        print("没有需要修复的订单行（幂等）。")
        return 0

    from crud.cloud_sync_outbox import ensure_cloud_sync_outbox_table

    ensure_cloud_sync_outbox_table()
    with get_engine().begin() as conn:
        result = apply_repairs(conn, plan, operator=args.operator, reason=reason)

    print(f"已取消 {int(result.get('lines') or 0)} 行，入队回传事件 {len(result.get('events') or [])} 个：")
    for event in result.get("events") or []:
        print(f"  event={event['event_type']} order={event['order_no']} payload={event['payload']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
