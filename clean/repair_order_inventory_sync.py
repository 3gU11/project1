#!/usr/bin/env python3
"""Repair order allocation and production/inventory mirror inconsistencies.

The command is preview-only by default. Applying changes requires exact candidate
counts from the preview, and creates database backup tables before any update.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
import sys
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine


RUN_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}$")
PROTECTED_STATES = ("待发货", "已出库", "已发货", "报废")

UNLOGGED_BINDINGS_SQL = """
SELECT
  u.unit_id,
  COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
  COALESCE(u.sales_id, '') AS order_no,
  COALESCE(u.contract_no, '') AS contract_no,
  COALESCE(fg.`状态`, '') AS inventory_status,
  COALESCE(fg.`Location_Code`, '') AS location_code
FROM finished_goods_data fg
JOIN units u
  ON TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no)) = TRIM(fg.`流水号`)
WHERE TRIM(COALESCE(fg.`状态`, '')) = '待发货'
  AND TRIM(COALESCE(fg.`占用订单号`, '')) = ''
  AND TRIM(COALESCE(u.sales_id, '')) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM transaction_log tl
    WHERE TRIM(tl.`流水号`) = TRIM(fg.`流水号`)
      AND tl.`操作类型` IN (
        CONCAT('配货锁定-', TRIM(u.sales_id)),
        CONCAT('配货锁定-', TRIM(u.sales_id), '-库存现货'),
        CONCAT('配货锁定-', TRIM(u.sales_id), '-在产预占')
      )
  )
  AND NOT EXISTS (
    SELECT 1 FROM sys_operation_log sol
    WHERE TRIM(COALESCE(sol.serial_no, '')) = TRIM(fg.`流水号`)
      AND TRIM(COALESCE(sol.order_no, '')) = TRIM(u.sales_id)
      AND sol.module = '订单配货'
      AND sol.action_type = '配货'
  )
ORDER BY serial_no
"""

MIRROR_MISMATCH_SQL = """
SELECT
  u.unit_id,
  COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
  COALESCE(u.contract_no, '') AS contract_no,
  COALESCE(u.customer, '') AS customer,
  COALESCE(u.dealer_name, '') AS dealer,
  COALESCE(u.order_remark, '') AS remark,
  COALESCE(u.sales_id, '') AS order_no
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
JOIN finished_goods_data fg
  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
WHERE b.status IN ('Confirmed', 'In_Production')
  AND TRIM(COALESCE(u.contract_no, '')) <> ''
  AND (
    TRIM(COALESCE(u.contract_no, '')) <> TRIM(COALESCE(fg.`合同号`, ''))
    OR TRIM(COALESCE(u.sales_id, '')) <> TRIM(COALESCE(fg.`占用订单号`, ''))
  )
  AND TRIM(COALESCE(fg.`状态`, '')) NOT LIKE '库存中%'
  AND TRIM(COALESCE(fg.`状态`, '')) NOT IN ('待发货', '已出库', '已发货', '报废')
ORDER BY serial_no
"""

COMPLETION_RISK_SQL = """
SELECT
  b.batch_code,
  b.status,
  COUNT(*) AS total_units,
  SUM(EXISTS(
    SELECT 1 FROM inbound_history ih
    WHERE TRIM(ih.serial_no) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
  )) AS historical_inbound_units,
  SUM(
    EXISTS(
      SELECT 1 FROM inbound_history ih
      WHERE TRIM(ih.serial_no) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
    )
    AND TRIM(COALESCE(fg.`状态`, '')) NOT IN ('', '待入库', '已绑定')
  ) AS currently_completed_units
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
LEFT JOIN finished_goods_data fg
  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
WHERE b.status = 'In_Production'
GROUP BY b.batch_id, b.batch_code, b.status
HAVING historical_inbound_units > currently_completed_units
ORDER BY b.batch_code
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("V8_REPAIR_DATABASE_URL", ""),
        help="SQLAlchemy MySQL URL; defaults to V8_REPAIR_DATABASE_URL",
    )
    parser.add_argument("--apply", action="store_true", help="apply the previewed repair")
    parser.add_argument("--rollback", metavar="RUN_ID", help="restore relationship fields from backup tables")
    parser.add_argument("--run-id", help="backup suffix in YYYYMMDD_HHMMSS format")
    parser.add_argument("--confirm-unlogged-count", type=int)
    parser.add_argument("--confirm-mirror-count", type=int)
    return parser.parse_args()


def require_database_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise SystemExit("Set V8_REPAIR_DATABASE_URL or pass --database-url; no local database default is used.")
    if not value.startswith(("mysql+pymysql://", "mysql://")):
        raise SystemExit("Only an explicit MySQL SQLAlchemy URL is accepted.")
    return value


def validate_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise SystemExit("RUN_ID must use YYYYMMDD_HHMMSS.")
    return value


def rows(conn: Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(sql)).mappings().all()]


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
        "units": f"repair_backup_unlogged_bindings_{run_id}_units",
        "inventory": f"repair_backup_unlogged_bindings_{run_id}_fg",
        "mirror": f"repair_backup_contract_mirror_{run_id}_fg",
    }


def preview_connection(conn: Connection) -> dict[str, Any]:
    unlogged = rows(conn, UNLOGGED_BINDINGS_SQL)
    mirrors = rows(conn, MIRROR_MISMATCH_SQL)
    risks = rows(conn, COMPLETION_RISK_SQL)
    return {
        "unlogged_binding_count": len(unlogged),
        "mirror_mismatch_count": len(mirrors),
        "unlogged_bindings": unlogged,
        "mirror_mismatches": mirrors,
        "completion_risks": risks,
    }


def preview(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        return preview_connection(conn)


def create_backups(engine: Engine, run_id: str, unlogged: list[dict[str, Any]], mirrors: list[dict[str, Any]]) -> dict[str, str]:
    names = backup_names(run_id)
    with engine.begin() as conn:
        existing = [name for name in names.values() if table_exists(conn, name)]
        if existing:
            raise RuntimeError(f"Backup tables already exist: {', '.join(existing)}")

        if unlogged:
            unit_ids = [row["unit_id"] for row in unlogged]
            serials = [row["serial_no"] for row in unlogged]
            conn.execute(
                text(f"CREATE TABLE {names['units']} AS SELECT * FROM units WHERE unit_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": unit_ids},
            )
            conn.execute(
                text(f"CREATE TABLE {names['inventory']} AS SELECT * FROM finished_goods_data WHERE `流水号` IN :sns")
                .bindparams(bindparam("sns", expanding=True)),
                {"sns": serials},
            )
        else:
            conn.execute(text(f"CREATE TABLE {names['units']} AS SELECT * FROM units WHERE 1=0"))
            conn.execute(text(f"CREATE TABLE {names['inventory']} AS SELECT * FROM finished_goods_data WHERE 1=0"))

        if mirrors:
            serials = [row["serial_no"] for row in mirrors]
            conn.execute(
                text(f"CREATE TABLE {names['mirror']} AS SELECT * FROM finished_goods_data WHERE `流水号` IN :sns")
                .bindparams(bindparam("sns", expanding=True)),
                {"sns": serials},
            )
        else:
            conn.execute(text(f"CREATE TABLE {names['mirror']} AS SELECT * FROM finished_goods_data WHERE 1=0"))
    return names


def apply_repair(engine: Engine, run_id: str, report: dict[str, Any]) -> dict[str, Any]:
    unlogged = report["unlogged_bindings"]
    mirrors = report["mirror_mismatches"]
    names = create_backups(engine, run_id, unlogged, mirrors)

    with engine.begin() as conn:
        for row in unlogged:
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=NULL, customer=NULL, dealer_id=NULL, dealer_name=NULL,
                        due_date=NULL, sales_id=NULL, order_remark=NULL, is_contract_pinned=0,
                        is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id
                """),
                {"unit_id": row["unit_id"]},
            )
            conn.execute(
                text("""
                    UPDATE finished_goods_data
                    SET `状态`=CASE
                          WHEN TRIM(COALESCE(`Location_Code`,''))<>''
                          THEN CONCAT('库存中（',TRIM(`Location_Code`),'）')
                          ELSE '待入库' END,
                        `占用订单号`=NULL, `客户`='', `代理商`='', `合同号`='',
                        `合同备注`='', `更新时间`=NOW()
                    WHERE `流水号`=:serial_no
                """),
                {"serial_no": row["serial_no"]},
            )
            conn.execute(
                text("""
                    INSERT INTO sys_operation_log
                      (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
                    VALUES
                      ('SystemRepair','SystemRepair',NOW(),'订单配货','数据纠错','机台',
                       :content,:serial_no,:order_no,:contract_no)
                """),
                {
                    "content": f"清理无人工配货证据的历史自动误绑；备份运行编号：{run_id}",
                    "serial_no": row["serial_no"],
                    "order_no": row["order_no"],
                    "contract_no": row["contract_no"],
                },
            )

        for row in mirrors:
            conn.execute(
                text("""
                    UPDATE finished_goods_data
                    SET `合同号`=:contract_no, `客户`=:customer, `代理商`=:dealer,
                        `合同备注`=:remark, `占用订单号`=:order_no, `更新时间`=NOW()
                    WHERE `流水号`=:serial_no
                """),
                row,
            )
            conn.execute(
                text("""
                    INSERT INTO sys_operation_log
                      (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
                    VALUES
                      ('SystemRepair','SystemRepair',NOW(),'库存同步','数据纠错','机台',
                       :content,:serial_no,:order_no,:contract_no)
                """),
                {
                    "content": f"按活动生产卡片补齐待入库镜像关系；备份运行编号：{run_id}",
                    "serial_no": row["serial_no"],
                    "order_no": row["order_no"],
                    "contract_no": row["contract_no"],
                },
            )

        # Verify through the same connection before committing. A failed check
        # rolls back all data updates and audit rows; backup tables remain.
        after = preview_connection(conn)
        if after["unlogged_binding_count"] or after["mirror_mismatch_count"]:
            raise RuntimeError(
                "Post-repair verification failed; data updates were rolled back: "
                f"unlogged={after['unlogged_binding_count']}, mirrors={after['mirror_mismatch_count']}"
            )
    return {"run_id": run_id, "backups": names, "after": after}


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
        for key in ("inventory", "mirror"):
            conn.execute(text(f"""
                UPDATE finished_goods_data fg JOIN {names[key]} b ON b.`流水号`=fg.`流水号`
                SET fg.`状态`=b.`状态`, fg.`占用订单号`=b.`占用订单号`,
                    fg.`客户`=b.`客户`, fg.`代理商`=b.`代理商`,
                    fg.`合同备注`=b.`合同备注`, fg.`合同号`=b.`合同号`,
                    fg.`更新时间`=NOW()
            """))
    return {"rolled_back": run_id, "backups_retained": names}


def main() -> int:
    args = parse_args()
    database_url = require_database_url(args.database_url)
    engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)

    if args.rollback:
        result = rollback(engine, validate_run_id(args.rollback))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    report = preview(engine)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not args.apply:
        return 0

    expected_unlogged = report["unlogged_binding_count"]
    expected_mirrors = report["mirror_mismatch_count"]
    if args.confirm_unlogged_count != expected_unlogged or args.confirm_mirror_count != expected_mirrors:
        raise SystemExit(
            "Apply refused: confirmation counts must exactly match the current preview "
            f"(--confirm-unlogged-count {expected_unlogged} --confirm-mirror-count {expected_mirrors})."
        )

    run_id = validate_run_id(args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    result = apply_repair(engine, run_id, report)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
