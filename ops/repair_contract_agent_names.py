"""回填历史合同里误填成客户联系人的「代理商」。

背景（2026-11-12）：在此之前「经销商订单转合同」弹窗把客户联系人（如「熊廷艳」）
预填进合同的「代理商」，转合同后扩散到 factory_plan / sales_orders /
finished_goods_data / contract_notifications / shipping_history / inbound_history。
新规则见 crud/local_contract_drafts.py:resolve_party_name：
    订单上记录的大区经理（一个订单只有一位，大区多经理也不歧义） > 经销商公司名。
客户联系人永远不参与「代理商 / 需方」取值。

用法：
    python ops/repair_contract_agent_names.py            # 只打印将要修改的行（默认）
    python ops/repair_contract_agent_names.py --apply    # 先备份到 data_repair_backups/ 再写入

只改「代理商 == 该订单客户联系人」或「注销占位名」的行，人工维护过的值不会被动到。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import get_engine  # noqa: E402
from crud.local_contract_drafts import INVALID_PARTY_NAMES  # noqa: E402

BACKUP_DIR = Path(__file__).resolve().parents[1] / "data_repair_backups"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _resolve_agent(manager: str, dealer: str) -> str:
    """与 resolve_party_name 同口径：大区经理 > 经销商公司名；占位名视为无效。"""
    for candidate in (_clean(manager), _clean(dealer)):
        if candidate and candidate not in INVALID_PARTY_NAMES:
            return candidate
    return ""


def _load_order_candidates(conn) -> list[dict[str, str]]:
    """每个订单一行：合同号、客户名、客户联系人、大区经理、经销商、应回填的代理商。"""
    rows = conn.execute(
        text(
            "SELECT contract_no, order_no, customer_name, contact_name, "
            "regional_manager_name, dealer_name FROM dealer_orders "
            "WHERE COALESCE(TRIM(contract_no), '') <> '' ORDER BY contract_no, order_no, line_no"
        )
    ).fetchall()
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for contract_no, order_no, customer_name, contact, manager, dealer in rows:
        key = (_clean(contract_no), _clean(order_no))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "contract_no": _clean(contract_no),
                "order_no": _clean(order_no),
                "customer_name": _clean(customer_name),
                "contact": _clean(contact),
                "manager": _clean(manager),
                "dealer": _clean(dealer),
                "resolved": _resolve_agent(_clean(manager), _clean(dealer)),
            }
        )
    return candidates


def _match_candidate(
    candidates: list[dict[str, str]],
    contract_no: str,
    agent: str,
    customer_name: str,
) -> tuple[dict[str, str] | None, str]:
    """按合同号 + 旧代理商找订单行；同合同多订单时优先客户名一致的。

    返回 (匹配结果, 跳过原因)。没有订单行可匹配时返回 (None, '')，说明这张合同
    不是云端经销商订单转出来的，不需要处理。
    """
    hits = [
        candidate
        for candidate in candidates
        if candidate["contract_no"] == contract_no
        and (candidate["contact"] == agent or agent in INVALID_PARTY_NAMES)
    ]
    if not hits:
        return None, ""
    exact = [candidate for candidate in hits if candidate["customer_name"] == customer_name]
    pool = exact or hits
    resolved_values = {candidate["resolved"] for candidate in pool if candidate["resolved"]}
    if not resolved_values:
        return None, f"{contract_no} {customer_name}: 订单没有可用的大区经理/经销商名，跳过"
    if len(resolved_values) != 1:
        return None, f"{contract_no} {customer_name}: 同合同多订单的代理商去向不一致，跳过"
    return {**pool[0], "old_agent": agent, "resolved": resolved_values.pop()}, ""


def _plan_changes() -> tuple[list[dict[str, Any]], list[str]]:
    with get_engine().connect() as conn:
        candidates = _load_order_candidates(conn)
        plan_rows = conn.execute(
            text(
                "SELECT `合同号`, `客户名`, `代理商`, COUNT(*) AS rows_count "
                "FROM factory_plan WHERE COALESCE(TRIM(`合同号`), '') <> '' "
                "GROUP BY `合同号`, `客户名`, `代理商`"
            )
        ).fetchall()
    targets: list[dict[str, Any]] = []
    skipped: list[str] = []
    for contract_no, customer_name, agent, rows_count in plan_rows:
        contract_no, customer_name, agent = _clean(contract_no), _clean(customer_name), _clean(agent)
        matched, reason = _match_candidate(candidates, contract_no, agent, customer_name)
        if not matched:
            if reason:
                skipped.append(reason)
            continue
        if matched["resolved"] == agent:
            continue
        targets.append(
            {
                "contract_no": contract_no,
                "customer_name": customer_name,
                "rows_count": int(rows_count or 0),
                "old_agent": agent,
                "new_agent": matched["resolved"],
                "manager": matched["manager"],
                "dealer": matched["dealer"],
                "contact": matched["contact"],
                "order_no": matched["order_no"],
            }
        )
    return targets, skipped


def _collect_backup(conn, contract_no: str) -> dict[str, Any]:
    backup: dict[str, Any] = {"contract_no": contract_no}
    tables = {
        "factory_plan": "SELECT * FROM factory_plan WHERE `合同号`=:cid",
        "sales_orders": (
            "SELECT o.* FROM sales_orders o JOIN factory_plan fp ON fp.`订单号`=o.`订单号` "
            "WHERE fp.`合同号`=:cid"
        ),
        "finished_goods_data": "SELECT * FROM finished_goods_data WHERE `合同号`=:cid",
        "contract_notifications": "SELECT * FROM contract_notifications WHERE contract_id=:cid",
        "shipping_history": "SELECT * FROM shipping_history WHERE `合同号`=:cid",
        "inbound_history": "SELECT * FROM inbound_history WHERE contract_no=:cid",
    }
    for name, sql in tables.items():
        try:
            rows = conn.execute(text(sql), {"cid": contract_no}).mappings().all()
            backup[name] = [dict(row) for row in rows]
        except Exception as exc:  # 备份缺一张表不影响修复，但要在日志里留痕
            backup[name] = {"error": str(exc)}
    return backup


def _repair_rows(conn, target: dict[str, Any]) -> dict[str, int]:
    contract_no = target["contract_no"]
    old_agent = target["old_agent"]
    new_agent = target["new_agent"]
    counts: dict[str, int] = {}
    statements = {
        "factory_plan": "UPDATE factory_plan SET `代理商`=:new WHERE `合同号`=:cid AND `代理商`=:old",
        "finished_goods_data": (
            "UPDATE finished_goods_data SET `代理商`=:new WHERE `合同号`=:cid AND `代理商`=:old"
        ),
        "sales_orders": (
            "UPDATE sales_orders SET `代理商`=:new WHERE `订单号` IN ("
            "SELECT `订单号` FROM factory_plan WHERE `合同号`=:cid"
            ") AND `代理商`=:old"
        ),
        "shipping_history": (
            "UPDATE shipping_history SET `代理商`=:new WHERE `合同号`=:cid AND `代理商`=:old"
        ),
        "inbound_history": (
            "UPDATE inbound_history SET dealer=:new WHERE contract_no=:cid AND dealer=:old"
        ),
    }
    params = {"cid": contract_no, "old": old_agent, "new": new_agent}
    for name, sql in statements.items():
        try:
            counts[name] = int(conn.execute(text(sql), params).rowcount or 0)
        except Exception as exc:
            counts[name] = -1
            print(f"  ! {name} 更新失败：{exc}")
    # 合同通知里的快照是 JSON，单独处理 dealer 字段
    try:
        rows = conn.execute(
            text("SELECT contract_id, created_snapshot, converted_snapshot FROM contract_notifications "
                 "WHERE contract_id=:cid"),
            {"cid": contract_no},
        ).mappings().all()
        updated = 0
        for row in rows:
            payload: dict[str, Any] = {}
            changed = False
            for column in ("created_snapshot", "converted_snapshot"):
                raw = row.get(column)
                if not raw:
                    continue
                try:
                    snapshot = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if _clean(snapshot.get("dealer")) == old_agent:
                    snapshot["dealer"] = new_agent
                    changed = True
                payload[column] = json.dumps(snapshot, ensure_ascii=False)
            if changed:
                conn.execute(
                    text("UPDATE contract_notifications SET created_snapshot=:created, "
                         "converted_snapshot=:converted WHERE contract_id=:cid"),
                    {
                        "created": payload.get("created_snapshot", row.get("created_snapshot")),
                        "converted": payload.get("converted_snapshot", row.get("converted_snapshot")),
                        "cid": contract_no,
                    },
                )
                updated += 1
        counts["contract_notifications"] = updated
    except Exception as exc:
        counts["contract_notifications"] = -1
        print(f"  ! contract_notifications 更新失败：{exc}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="回填历史合同的代理商为客户联系人的问题")
    parser.add_argument("--apply", action="store_true", help="备份后真正写入（默认只预览）")
    args = parser.parse_args()

    targets, skipped = _plan_changes()
    for warning in skipped:
        print(f"跳过：{warning}")
    if not targets:
        print("没有需要修复的合同。")
        return 0

    print(f"\n待修复合同/代理商 {len(targets)} 组：")
    for target in targets:
        print(
            f"  {target['contract_no']} {target['customer_name']}: "
            f"代理商 {target['old_agent']!r} → {target['new_agent']!r} "
            f"(订单 {target['order_no']}, 大区经理={target['manager']!r}, "
            f"经销商={target['dealer']!r}, 联系人={target['contact']!r}, {target['rows_count']} 行)"
        )

    if not args.apply:
        print("\n当前是预览模式；确认无误后加 --apply 备份并写入。")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"repair_agent_names_{stamp}.json"
    backup: dict[str, Any] = {"created_at": stamp, "contracts": []}

    with get_engine().begin() as conn:
        for contract_no in sorted({target["contract_no"] for target in targets}):
            backup["contracts"].append(_collect_backup(conn, contract_no))
        backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n已备份 {len(backup['contracts'])} 张合同原始数据 → {backup_path}")

        for target in targets:
            counts = _repair_rows(conn, target)
            print(f"  {target['contract_no']} ({target['old_agent']} → {target['new_agent']}): {counts}")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
