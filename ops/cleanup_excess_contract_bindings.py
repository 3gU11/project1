#!/usr/bin/env python3
"""Clean excess contract bindings created by legacy order synchronization.

The command is preview-only by default. It only selects over-plan contract/model
groups whose planned quantity is fully covered by machines with allocation
evidence. Applying requires both the preview count and fingerprint.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import sys
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine


RUN_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
PROTECTED_STATES = {"待发货", "已出库", "已发货", "报废"}

PLAN_ROWS_SQL = """
SELECT `合同号` AS contract_no, `机型` AS model_type, `排产数量` AS plan_qty
FROM factory_plan
WHERE TRIM(COALESCE(`合同号`, '')) <> ''
  AND TRIM(COALESCE(`机型`, '')) <> ''
"""

UNIT_ROWS_SQL = """
SELECT
  u.unit_id,
  TRIM(COALESCE(u.contract_no, '')) AS contract_no,
  TRIM(COALESCE(u.model_type, '')) AS model_type,
  COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) AS serial_no,
  b.batch_code,
  COALESCE(u.sales_id, '') AS sales_id,
  COALESCE(u.is_locked, 0) AS is_locked,
  COALESCE(u.is_contract_pinned, 0) AS is_contract_pinned,
  u.created_at,
  u.updated_at,
  CASE WHEN fg.`流水号` IS NULL THEN 0 ELSE 1 END AS has_inventory,
  COALESCE(fg.`状态`, '') AS inventory_status,
  COALESCE(fg.`占用订单号`, '') AS inventory_order_no,
  EXISTS (
    SELECT 1
    FROM transaction_log tl
    WHERE TRIM(tl.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
      AND tl.`操作类型` LIKE '配货锁定-%'
  ) AS has_allocation_transaction,
  EXISTS (
    SELECT 1
    FROM sys_operation_log sol
    WHERE TRIM(COALESCE(sol.serial_no, '')) =
          TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
      AND sol.module = '订单配货'
      AND sol.action_type = '配货'
  ) AS has_allocation_audit
FROM units u
LEFT JOIN batches b ON b.batch_id = u.batch_id
LEFT JOIN finished_goods_data fg
  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
WHERE TRIM(COALESCE(u.contract_no, '')) <> ''
  AND TRIM(COALESCE(u.model_type, '')) <> ''
ORDER BY contract_no, model_type, batch_code, serial_no, unit_id
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("V8_REPAIR_DATABASE_URL", ""),
        help="explicit SQLAlchemy MySQL URL; defaults to V8_REPAIR_DATABASE_URL",
    )
    parser.add_argument("--apply", action="store_true", help="apply the previewed cleanup")
    parser.add_argument("--rollback", metavar="RUN_ID", help="restore fields from backup tables")
    parser.add_argument("--run-id", help="backup suffix in YYYYMMDD_HHMMSS format")
    parser.add_argument("--confirm-count", type=int)
    parser.add_argument("--confirm-fingerprint")
    return parser.parse_args()


def require_database_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise SystemExit("Set V8_REPAIR_DATABASE_URL or pass --database-url; no default database is used.")
    if not value.startswith(("mysql+pymysql://", "mysql://")):
        raise SystemExit("Only an explicit MySQL SQLAlchemy URL is accepted.")
    return value


def validate_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise SystemExit("RUN_ID must use YYYYMMDD_HHMMSS.")
    return value


def positive_quantity(value: Any) -> int:
    try:
        quantity = int(Decimal(str(value or "0").strip()))
    except (InvalidOperation, ValueError):
        return 0
    return max(quantity, 0)


def is_protected_state(value: Any) -> bool:
    state = str(value or "").strip()
    return state in PROTECTED_STATES or state.startswith("库存中")


def has_allocation_evidence(row: dict[str, Any]) -> bool:
    return any(
        (
            str(row.get("sales_id") or "").strip(),
            str(row.get("inventory_order_no") or "").strip(),
            bool(row.get("is_locked")),
            bool(row.get("is_contract_pinned")),
            bool(row.get("has_allocation_transaction")),
            bool(row.get("has_allocation_audit")),
            is_protected_state(row.get("inventory_status")),
        )
    )


def is_clearable(row: dict[str, Any]) -> bool:
    return bool(
        str(row.get("unit_id") or "").strip()
        and str(row.get("serial_no") or "").strip()
        and str(row.get("batch_code") or "").strip()
        and bool(row.get("has_inventory"))
        and not has_allocation_evidence(row)
    )


def candidate_fingerprint(candidates: list[dict[str, Any]]) -> str:
    values = [
        "|".join(
            (
                str(row.get("unit_id") or "").strip(),
                str(row.get("serial_no") or "").strip(),
                str(row.get("contract_no") or "").strip(),
                str(row.get("model_type") or "").strip(),
            )
        )
        for row in candidates
    ]
    return hashlib.sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def classify_candidates(
    plan_rows: list[dict[str, Any]], unit_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    plan_by_key: dict[tuple[str, str], int] = defaultdict(int)
    for row in plan_rows:
        key = (
            str(row.get("contract_no") or "").strip(),
            str(row.get("model_type") or "").strip(),
        )
        if all(key):
            plan_by_key[key] += positive_quantity(row.get("plan_qty"))

    units_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in unit_rows:
        item = dict(row)
        key = (
            str(item.get("contract_no") or "").strip(),
            str(item.get("model_type") or "").strip(),
        )
        if all(key):
            units_by_key[key].append(item)

    candidates: list[dict[str, Any]] = []
    accepted_groups: list[dict[str, Any]] = []
    rejected_groups: list[dict[str, Any]] = []
    for key, group_rows in sorted(units_by_key.items()):
        plan_qty = plan_by_key.get(key, 0)
        unit_qty = len(group_rows)
        if plan_qty <= 0 or unit_qty <= plan_qty:
            continue
        protected = [row for row in group_rows if has_allocation_evidence(row)]
        clearable = [row for row in group_rows if is_clearable(row)]
        excess = unit_qty - plan_qty
        summary = {
            "contract_no": key[0],
            "model_type": key[1],
            "plan_qty": plan_qty,
            "unit_qty": unit_qty,
            "excess_qty": excess,
            "protected_qty": len(protected),
            "clearable_qty": len(clearable),
            "unclassified_qty": unit_qty - len(protected) - len(clearable),
        }
        # Every retained row must have positive allocation evidence, and every
        # excess row must independently satisfy the conservative clearable rule.
        if len(protected) == plan_qty and len(clearable) == excess and summary["unclassified_qty"] == 0:
            accepted_groups.append(summary)
            candidates.extend(clearable)
        else:
            rejected_groups.append(summary)

    candidates.sort(
        key=lambda row: (
            str(row.get("batch_code") or ""),
            str(row.get("serial_no") or ""),
            str(row.get("unit_id") or ""),
        )
    )
    return {
        "candidate_count": len(candidates),
        "fingerprint": candidate_fingerprint(candidates),
        "accepted_groups": accepted_groups,
        "rejected_over_plan_groups": rejected_groups,
        "candidates": candidates,
    }


def rows(conn: Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(sql)).mappings().all()]


def preview_connection(conn: Connection) -> dict[str, Any]:
    return classify_candidates(rows(conn, PLAN_ROWS_SQL), rows(conn, UNIT_ROWS_SQL))


def preview(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        return preview_connection(conn)


def table_exists(conn: Connection, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=:table_name"
            ),
            {"table_name": table_name},
        ).scalar()
    )


def backup_names(run_id: str) -> dict[str, str]:
    return {
        "units": f"repair_backup_excess_contract_{run_id}_units",
        "inventory": f"repair_backup_excess_contract_{run_id}_fg",
        "ledger": f"repair_backup_excess_contract_{run_id}_ledger",
    }


def create_backups(engine: Engine, run_id: str, candidates: list[dict[str, Any]]) -> dict[str, str]:
    if not candidates:
        raise RuntimeError("No candidates to back up.")
    names = backup_names(run_id)
    unit_ids = [row["unit_id"] for row in candidates]
    serials = [row["serial_no"] for row in candidates]
    with engine.begin() as conn:
        existing = [name for name in names.values() if table_exists(conn, name)]
        if existing:
            raise RuntimeError(f"Backup tables already exist: {', '.join(existing)}")
        conn.execute(
            text(f"CREATE TABLE {names['units']} AS SELECT * FROM units WHERE unit_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": unit_ids},
        )
        conn.execute(
            text(
                f"CREATE TABLE {names['inventory']} AS "
                "SELECT * FROM finished_goods_data WHERE `流水号` IN :serials"
            ).bindparams(bindparam("serials", expanding=True)),
            {"serials": serials},
        )
        conn.execute(
            text(
                f"CREATE TABLE {names['ledger']} AS "
                "SELECT * FROM production_history_ledger WHERE unit_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": unit_ids},
        )
    return names


def apply_cleanup(engine: Engine, run_id: str, report: dict[str, Any]) -> dict[str, Any]:
    candidates = report["candidates"]
    names = create_backups(engine, run_id, candidates)
    with engine.begin() as conn:
        current = preview_connection(conn)
        if (
            current["candidate_count"] != report["candidate_count"]
            or current["fingerprint"] != report["fingerprint"]
        ):
            raise RuntimeError("Candidate set changed after backup; cleanup was not applied.")

        updated_units = 0
        updated_inventory = 0
        updated_ledger = 0
        for row in candidates:
            params = {
                "unit_id": row["unit_id"],
                "serial_no": row["serial_no"],
                "contract_no": row["contract_no"],
                "content": f"清理旧订单同步产生的超计划合同绑定；备份运行编号：{run_id}",
            }
            result = conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=NULL, customer=NULL, dealer_id=NULL, dealer_name=NULL,
                        due_date=NULL, sales_id=NULL, order_remark=NULL,
                        is_contract_pinned=0, is_locked=0, locked_by=NULL, locked_at=NULL,
                        updated_at=NOW()
                    WHERE unit_id=:unit_id
                      AND TRIM(COALESCE(contract_no, ''))=:contract_no
                      AND TRIM(COALESCE(sales_id, ''))=''
                      AND COALESCE(is_locked, 0)=0
                      AND COALESCE(is_contract_pinned, 0)=0
                """),
                params,
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Unit safety check failed for {row['unit_id']}; transaction rolled back.")
            updated_units += 1

            result = conn.execute(
                text("""
                    UPDATE finished_goods_data
                    SET `占用订单号`=NULL, `客户`='', `代理商`='', `合同号`='',
                        `合同备注`='', `更新时间`=NOW()
                    WHERE TRIM(`流水号`)=TRIM(:serial_no)
                      AND TRIM(COALESCE(`合同号`, ''))=:contract_no
                      AND TRIM(COALESCE(`占用订单号`, ''))=''
                      AND TRIM(COALESCE(`状态`, '')) NOT IN ('待发货','已出库','已发货','报废')
                      AND TRIM(COALESCE(`状态`, '')) NOT LIKE '库存中%'
                """),
                params,
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Inventory safety check failed for {row['serial_no']}; transaction rolled back.")
            updated_inventory += 1

            result = conn.execute(
                text("""
                    UPDATE production_history_ledger
                    SET contract_no=NULL, customer=NULL, dealer_name=NULL, order_remark=NULL,
                        updated_at=NOW()
                    WHERE unit_id=:unit_id
                      AND TRIM(COALESCE(contract_no, ''))=:contract_no
                """),
                params,
            )
            updated_ledger += int(result.rowcount or 0)
            conn.execute(
                text("""
                    INSERT INTO sys_operation_log
                      (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
                    VALUES
                      ('SystemRepair','SystemRepair',NOW(),'合同绑定','数据纠错','机台',
                       :content,:serial_no,'',:contract_no)
                """),
                params,
            )

        after = preview_connection(conn)
        if after["candidate_count"]:
            raise RuntimeError(
                f"Post-cleanup verification found {after['candidate_count']} candidates; transaction rolled back."
            )
    return {
        "run_id": run_id,
        "backups": names,
        "updated_units": updated_units,
        "updated_inventory": updated_inventory,
        "updated_ledger": updated_ledger,
        "after_candidate_count": after["candidate_count"],
    }


def rollback(engine: Engine, run_id: str) -> dict[str, Any]:
    names = backup_names(run_id)
    with engine.begin() as conn:
        missing = [name for name in names.values() if not table_exists(conn, name)]
        if missing:
            raise RuntimeError(f"Missing rollback tables: {', '.join(missing)}")
        conn.execute(text(f"""
            UPDATE units u JOIN {names['units']} b ON b.unit_id=u.unit_id
            SET u.contract_no=b.contract_no, u.customer=b.customer, u.dealer_id=b.dealer_id,
                u.dealer_name=b.dealer_name, u.due_date=b.due_date, u.sales_id=b.sales_id,
                u.order_remark=b.order_remark, u.is_contract_pinned=b.is_contract_pinned,
                u.is_locked=b.is_locked, u.locked_by=b.locked_by, u.locked_at=b.locked_at,
                u.updated_at=NOW()
        """))
        conn.execute(text(f"""
            UPDATE finished_goods_data fg
            JOIN {names['inventory']} b ON b.`流水号`=fg.`流水号`
            SET fg.`占用订单号`=b.`占用订单号`, fg.`客户`=b.`客户`,
                fg.`代理商`=b.`代理商`, fg.`合同号`=b.`合同号`,
                fg.`合同备注`=b.`合同备注`, fg.`更新时间`=NOW()
        """))
        conn.execute(text(f"""
            UPDATE production_history_ledger ph
            JOIN {names['ledger']} b ON b.id=ph.id
            SET ph.contract_no=b.contract_no, ph.customer=b.customer,
                ph.dealer_name=b.dealer_name, ph.order_remark=b.order_remark,
                ph.updated_at=NOW()
        """))
    return {"rolled_back": run_id, "backups_retained": names}


def main() -> int:
    args = parse_args()
    database_url = require_database_url(args.database_url)
    engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)

    if args.rollback:
        print(json.dumps(rollback(engine, validate_run_id(args.rollback)), ensure_ascii=False, indent=2))
        return 0

    report = preview(engine)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not args.apply:
        return 0
    fingerprint = str(args.confirm_fingerprint or "").strip().lower()
    if args.confirm_count != report["candidate_count"] or fingerprint != report["fingerprint"]:
        raise SystemExit(
            "Apply refused: --confirm-count and --confirm-fingerprint must exactly match the current preview."
        )
    if not FINGERPRINT_RE.fullmatch(fingerprint):
        raise SystemExit("Apply refused: invalid fingerprint format.")
    run_id = validate_run_id(args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    print(json.dumps(apply_cleanup(engine, run_id, report), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
