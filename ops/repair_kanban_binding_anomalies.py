#!/usr/bin/env python3
"""Repair the audited legacy kanban relationship anomalies from 2026-09-18.

Preview is the default. Apply requires the exact candidate count and fingerprint.
Every target is guarded by its audited contract/order pair, and backup tables are
created before updates. Historical operation and inbound records are retained.
"""

from __future__ import annotations

import argparse
from datetime import datetime
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

ORDER_ONLY = {
    "96-09-216": ("HT202609170001", "SO-20260917-343D"),
    "96-08-219": ("HT202608290003", "SO-20260918-F36A"),
    "96-08-220": ("HT202608290003", "SO-20260918-F36A"),
    "96-09-184": ("HT202608290003", "SO-20260918-F36A"),
    "96-09-185": ("HT202608290003", "SO-20260918-F36A"),
}

CLEAR_ALL = {
    "96-09-217": ("HT202609170004", "SO-20260917-BD8F"),
    "96-09-181": ("HT202609170005", "SO-20260917-A924"),
    "96-09-182": ("HT202609170005", "SO-20260917-A924"),
    "96-09-183": ("HT202609170005", "SO-20260917-A924"),
}

CLEAR_UNITS = {
    "BATCH-202607-AUTO-MANUAL-026-724647-STK-1782946149844003300-006":
        ("HT202605236659", "SO-20260720-6019"),
    "BATCH-202607-AUTO-MANUAL-026-724647-STK-1782946149844003300-007":
        ("HT202607140004", "SO-20260722-3682"),
    "BATCH-202609-AUTO-005-08063508-S13": ("HT202609110006", ""),
    "BATCH-202609-AUTO-005-08063508-S14": ("HT202609110006", ""),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("V8_REPAIR_DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", metavar="RUN_ID")
    parser.add_argument("--run-id")
    parser.add_argument("--confirm-count", type=int)
    parser.add_argument("--confirm-fingerprint")
    return parser.parse_args()


def require_database_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise SystemExit("Set V8_REPAIR_DATABASE_URL or pass --database-url.")
    if not value.startswith(("mysql+pymysql://", "mysql://")):
        raise SystemExit("Only an explicit MySQL SQLAlchemy URL is accepted.")
    return value


def validate_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise SystemExit("RUN_ID must use YYYYMMDD_HHMMSS.")
    return value


def backup_names(run_id: str) -> dict[str, str]:
    return {
        "units": f"repair_backup_kanban_binding_{run_id}_units",
        "inventory": f"repair_backup_kanban_binding_{run_id}_fg",
        "ledger": f"repair_backup_kanban_binding_{run_id}_ledger",
        "orders": f"repair_backup_kanban_binding_{run_id}_orders",
    }


def table_exists(conn: Connection, name: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=DATABASE() AND table_name=:name"
    ), {"name": name}).scalar())


def load_targets(conn: Connection) -> list[dict[str, Any]]:
    serial_targets = {**ORDER_ONLY, **CLEAR_ALL}
    serials = list(serial_targets)
    unit_ids = list(CLEAR_UNITS)
    serial_rows = conn.execute(text("""
        SELECT u.unit_id,
               COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) AS serial_no,
               TRIM(COALESCE(u.contract_no, '')) AS contract_no,
               TRIM(COALESCE(u.sales_id, '')) AS sales_id,
               u.model_type, b.batch_code, b.status AS batch_status,
               fg.`流水号` AS inventory_serial_no,
               TRIM(COALESCE(fg.`状态`, '')) AS inventory_status,
               TRIM(COALESCE(fg.`Location_Code`, '')) AS location_code
        FROM units u
        JOIN batches b ON b.batch_id=u.batch_id
        LEFT JOIN finished_goods_data fg
          ON TRIM(fg.`流水号`)=TRIM(COALESCE(NULLIF(u.serial_no, ''),u.forecast_serial_no))
        WHERE COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) IN :serials
    """).bindparams(bindparam("serials", expanding=True)), {"serials": serials}).mappings().all()
    unit_rows = conn.execute(text("""
        SELECT u.unit_id,
               COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) AS serial_no,
               TRIM(COALESCE(u.contract_no, '')) AS contract_no,
               TRIM(COALESCE(u.sales_id, '')) AS sales_id,
               u.model_type, b.batch_code, b.status AS batch_status,
               '' AS inventory_serial_no,
               '' AS inventory_status, '' AS location_code
        FROM units u JOIN batches b ON b.batch_id=u.batch_id
        WHERE u.unit_id IN :unit_ids
    """).bindparams(bindparam("unit_ids", expanding=True)), {"unit_ids": unit_ids}).mappings().all()

    found: dict[str, dict[str, Any]] = {}
    duplicate_keys: set[str] = set()
    for source in (serial_rows, unit_rows):
        for raw in source:
            row = dict(raw)
            key = str(row.get("serial_no") or row["unit_id"]).strip()
            if key in found:
                duplicate_keys.add(key)
            found[key] = row

    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    for action, target_map in (("clear_order", ORDER_ONLY), ("clear_all", CLEAR_ALL), ("clear_unit", CLEAR_UNITS)):
        for key, expected in target_map.items():
            row = found.get(key)
            if not row:
                errors.append(f"missing target: {key}")
                continue
            if key in duplicate_keys:
                errors.append(f"target is not unique in units: {key}")
                continue
            actual = (row["contract_no"], row["sales_id"])
            if actual != expected:
                errors.append(f"target drifted: {key}, expected={expected}, actual={actual}")
                continue
            if action != "clear_unit" and row["location_code"]:
                errors.append(f"target has physical location and is protected: {key}")
                continue
            if action != "clear_unit" and not row["inventory_serial_no"]:
                errors.append(f"target has no inventory mirror: {key}")
                continue
            row["action"] = action
            candidates.append(row)
    if errors:
        raise RuntimeError("; ".join(errors))
    return sorted(candidates, key=lambda row: (row["action"], str(row.get("serial_no") or row["unit_id"])))


def fingerprint(candidates: list[dict[str, Any]]) -> str:
    lines = ["|".join((
        row["action"], str(row["unit_id"]), str(row.get("serial_no") or ""),
        str(row["contract_no"]), str(row["sales_id"]),
    )) for row in candidates]
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def preview_connection(conn: Connection) -> dict[str, Any]:
    candidates = load_targets(conn)
    return {"candidate_count": len(candidates), "fingerprint": fingerprint(candidates), "candidates": candidates}


def create_backups(engine: Engine, run_id: str, report: dict[str, Any]) -> dict[str, str]:
    names = backup_names(run_id)
    unit_ids = [row["unit_id"] for row in report["candidates"]]
    serials = [
        row["serial_no"] for row in report["candidates"]
        if row["action"] in {"clear_order", "clear_all"}
    ]
    order_ids = sorted({row["sales_id"] for row in report["candidates"] if row.get("sales_id")})
    with engine.begin() as conn:
        existing = [name for name in names.values() if table_exists(conn, name)]
        if existing:
            raise RuntimeError(f"Backup tables already exist: {', '.join(existing)}")
        conn.execute(text(f"CREATE TABLE {names['units']} AS SELECT * FROM units WHERE unit_id IN :ids")
                     .bindparams(bindparam("ids", expanding=True)), {"ids": unit_ids})
        conn.execute(text(f"CREATE TABLE {names['inventory']} AS SELECT * FROM finished_goods_data WHERE `流水号` IN :sns")
                     .bindparams(bindparam("sns", expanding=True)), {"sns": serials})
        conn.execute(text(f"CREATE TABLE {names['ledger']} AS SELECT * FROM production_history_ledger WHERE unit_id IN :ids")
                     .bindparams(bindparam("ids", expanding=True)), {"ids": unit_ids})
        conn.execute(text(f"CREATE TABLE {names['orders']} AS SELECT * FROM sales_orders WHERE `订单号` IN :orders")
                     .bindparams(bindparam("orders", expanding=True)), {"orders": order_ids})
    return names


def update_inventory_mirror(conn: Connection, row: dict[str, Any], *, clear_contract: bool) -> None:
    params = {
        "serial_no": row["serial_no"],
        "contract_no": row["contract_no"],
        "sales_id": row["sales_id"],
    }
    contract_updates = "`客户`='', `代理商`='', `合同号`='', `合同备注`=''," if clear_contract else ""
    result = conn.execute(text(f"""
        UPDATE finished_goods_data SET `状态`='待入库', `占用订单号`=NULL,
            {contract_updates} `更新时间`=NOW()
        WHERE TRIM(`流水号`)=TRIM(:serial_no)
          AND TRIM(COALESCE(`合同号`,''))=:contract_no
          AND TRIM(COALESCE(`占用订单号`,''))=:sales_id
          AND TRIM(COALESCE(`Location_Code`,''))=''
    """), params)
    if result.rowcount != 1:
        raise RuntimeError(f"inventory guard failed: {row['serial_no']}, rows={result.rowcount}")


def clear_all_relationships(conn: Connection, row: dict[str, Any]) -> None:
    params = {"unit_id": row["unit_id"], "serial_no": row.get("serial_no") or "",
              "contract_no": row["contract_no"], "sales_id": row["sales_id"]}
    result = conn.execute(text("""
        UPDATE units SET contract_no=NULL, customer=NULL, dealer_id=NULL, dealer_name=NULL,
            due_date=NULL, sales_id=NULL, order_remark=NULL, is_contract_pinned=0,
            is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
        WHERE unit_id=:unit_id AND TRIM(COALESCE(contract_no,''))=:contract_no
          AND TRIM(COALESCE(sales_id,''))=:sales_id
    """), params)
    if result.rowcount != 1:
        raise RuntimeError(f"unit guard failed: {row['unit_id']}")
    if row["action"] == "clear_all":
        update_inventory_mirror(conn, row, clear_contract=True)
    conn.execute(text("""
        UPDATE production_history_ledger SET contract_no=NULL, customer=NULL,
            dealer_name=NULL, order_remark=NULL, updated_at=NOW()
        WHERE unit_id=:unit_id AND TRIM(COALESCE(contract_no,''))=:contract_no
    """), params)


def apply_repair(engine: Engine, run_id: str, report: dict[str, Any]) -> dict[str, Any]:
    names = create_backups(engine, run_id, report)
    with engine.begin() as conn:
        current = preview_connection(conn)
        if current["candidate_count"] != report["candidate_count"] or current["fingerprint"] != report["fingerprint"]:
            raise RuntimeError("Candidate set changed after backup; repair was not applied.")
        for row in current["candidates"]:
            params = {"unit_id": row["unit_id"], "serial_no": row.get("serial_no") or "",
                      "contract_no": row["contract_no"], "sales_id": row["sales_id"]}
            if row["action"] == "clear_order":
                result = conn.execute(text("""
                    UPDATE units SET sales_id=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id AND TRIM(COALESCE(contract_no,''))=:contract_no
                      AND TRIM(COALESCE(sales_id,''))=:sales_id
                """), params)
                if result.rowcount != 1:
                    raise RuntimeError(f"order-only guard failed: {row['unit_id']}")
                update_inventory_mirror(conn, row, clear_contract=False)
            else:
                clear_all_relationships(conn, row)
            conn.execute(text("""
                INSERT INTO sys_operation_log
                  (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
                VALUES ('SystemRepair','SystemRepair',NOW(),'生产看板','数据纠错','机台',
                  :content,:serial_no,:sales_id,:contract_no)
            """), {**params, "content": f"清理旧订单同步/重算产生的异常关系；动作={row['action']}；备份运行编号={run_id}"})

        order_result = conn.execute(text("""
            UPDATE sales_orders SET status='active'
            WHERE `订单号`='SO-20260917-343D' AND status IN ('ready','allocated')
        """))
        if order_result.rowcount != 1:
            status = conn.execute(text(
                "SELECT status FROM sales_orders WHERE `订单号`='SO-20260917-343D'"
            )).scalar()
            if status != "active":
                raise RuntimeError(f"order status guard failed: SO-20260917-343D status={status!r}")

        remaining = 0
        for row in current["candidates"]:
            expected_contract = row["contract_no"] if row["action"] == "clear_order" else ""
            remaining += int(conn.execute(text("""
                SELECT COUNT(*) FROM units WHERE unit_id=:unit_id
                  AND (TRIM(COALESCE(sales_id,''))<>'' OR TRIM(COALESCE(contract_no,''))<>:contract_no)
            """), {"unit_id": row["unit_id"], "contract_no": expected_contract}).scalar() or 0)
        if remaining:
            raise RuntimeError(f"Post-repair verification failed for {remaining} targets; transaction rolled back.")
        inventory_remaining = int(conn.execute(text("""
            SELECT COUNT(*) FROM finished_goods_data
            WHERE `流水号` IN :serials
              AND (TRIM(COALESCE(`占用订单号`,''))<>'' OR `状态`<>'待入库')
        """).bindparams(bindparam("serials", expanding=True)), {
            "serials": list(ORDER_ONLY) + list(CLEAR_ALL),
        }).scalar() or 0)
        if inventory_remaining:
            raise RuntimeError(
                f"Post-repair inventory verification failed for {inventory_remaining} targets; transaction rolled back."
            )
    return {"run_id": run_id, "backups": names, "updated_count": report["candidate_count"]}


def rollback(engine: Engine, run_id: str) -> dict[str, Any]:
    names = backup_names(run_id)
    with engine.begin() as conn:
        missing = [name for name in names.values() if not table_exists(conn, name)]
        if missing:
            raise RuntimeError(f"Missing rollback tables: {', '.join(missing)}")
        conn.execute(text(f"""UPDATE units u JOIN {names['units']} b ON b.unit_id=u.unit_id
            SET u.serial_no=b.serial_no,u.forecast_serial_no=b.forecast_serial_no,u.contract_no=b.contract_no,
                u.customer=b.customer,u.dealer_id=b.dealer_id,u.dealer_name=b.dealer_name,u.due_date=b.due_date,
                u.sales_id=b.sales_id,u.order_remark=b.order_remark,u.is_contract_pinned=b.is_contract_pinned,
                u.is_locked=b.is_locked,u.locked_by=b.locked_by,u.locked_at=b.locked_at,u.updated_at=NOW()"""))
        conn.execute(text(f"""UPDATE finished_goods_data fg JOIN {names['inventory']} b ON b.`流水号`=fg.`流水号`
            SET fg.`状态`=b.`状态`,fg.`占用订单号`=b.`占用订单号`,fg.`客户`=b.`客户`,
                fg.`代理商`=b.`代理商`,fg.`合同号`=b.`合同号`,fg.`合同备注`=b.`合同备注`,fg.`更新时间`=NOW()"""))
        conn.execute(text(f"""UPDATE production_history_ledger ph JOIN {names['ledger']} b ON b.id=ph.id
            SET ph.contract_no=b.contract_no,ph.customer=b.customer,ph.dealer_name=b.dealer_name,
                ph.order_remark=b.order_remark,ph.updated_at=NOW()"""))
        conn.execute(text(f"""UPDATE sales_orders so JOIN {names['orders']} b ON b.`订单号`=so.`订单号`
            SET so.status=b.status"""))
        conn.execute(text(f"""
            INSERT INTO sys_operation_log
              (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
            SELECT 'SystemRepair','SystemRepair',NOW(),'生产看板','数据纠错回滚','机台',
              :content,COALESCE(NULLIF(TRIM(b.serial_no),''),TRIM(b.forecast_serial_no)),
              COALESCE(b.sales_id,''),COALESCE(b.contract_no,'')
            FROM {names['units']} b
        """), {"content": f"回滚生产看板异常关系修复；备份运行编号={run_id}"})
    return {"rolled_back": run_id, "backups_retained": names}


def main() -> int:
    args = parse_args()
    engine = create_engine(require_database_url(args.database_url), pool_pre_ping=True, pool_recycle=3600)
    if args.rollback:
        print(json.dumps(rollback(engine, validate_run_id(args.rollback)), ensure_ascii=False, indent=2))
        return 0
    with engine.connect() as conn:
        report = preview_connection(conn)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not args.apply:
        return 0
    supplied = str(args.confirm_fingerprint or "").strip().lower()
    if args.confirm_count != report["candidate_count"] or supplied != report["fingerprint"]:
        raise SystemExit("Apply refused: count and fingerprint must exactly match the preview.")
    if not FINGERPRINT_RE.fullmatch(supplied):
        raise SystemExit("Apply refused: invalid fingerprint.")
    run_id = validate_run_id(args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    print(json.dumps(apply_repair(engine, run_id, report), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
