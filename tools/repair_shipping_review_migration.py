import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pymysql


MYSQL_BASE = Path(r"C:\Program Files\MySQL\MySQL Server 8.0")


REPAIR_SQL = r"""
SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

{insert_missing_orders_sql}

{restore_finished_goods_orders_sql}

{restore_factory_plan_orders_sql}

{restore_finished_goods_contracts_sql}

{insert_shipping_history_sql}
"""


INSERT_MISSING_ORDERS_SQL = r"""
INSERT INTO {target}.sales_orders (
  `订单号`, `客户名`, `代理商`, `需求机型`, `需求数量`, `下单时间`, `备注`,
  `包装选项`, `发货时间`, `指定批次/来源`, `status`, `delete_reason`
)
SELECT
  CAST(s.`订单号` AS CHAR) COLLATE utf8mb4_general_ci,
  COALESCE(CAST(s.`客户名` AS CHAR), ''),
  COALESCE(CAST(s.`代理商` AS CHAR), ''),
  COALESCE(CAST(s.`需求机型` AS CHAR), ''),
  COALESCE(s.`需求数量`, 0),
  s.`下单时间`,
  COALESCE(CAST(s.`备注` AS CHAR), ''),
  COALESCE(CAST(s.`包装选项` AS CHAR), ''),
  s.`发货时间`,
  CASE
    WHEN s.`指定批次/来源` IS NOT NULL
      AND JSON_VALID(CAST(s.`指定批次/来源` AS CHAR))
    THEN JSON_EXTRACT(CAST(s.`指定批次/来源` AS CHAR), '$')
    ELSE JSON_OBJECT()
  END,
  COALESCE(NULLIF(TRIM(CAST(s.`status` AS CHAR)), ''), 'active'),
  COALESCE(CAST(s.`delete_reason` AS CHAR), '')
FROM {source}.sales_orders s
LEFT JOIN {target}.sales_orders t
  ON t.`订单号` = s.`订单号`
WHERE t.`订单号` IS NULL
  AND COALESCE(TRIM(CAST(s.`订单号` AS CHAR)), '') <> '';
"""


RESTORE_FINISHED_GOODS_ORDERS_SQL = r"""
UPDATE {target}.finished_goods_data fg
JOIN {source}.finished_goods_data src
  ON src.`流水号` = fg.`流水号`
JOIN {target}.sales_orders so
  ON so.`订单号` = src.`占用订单号`
SET fg.`占用订单号` = CAST(src.`占用订单号` AS CHAR)
WHERE COALESCE(TRIM(CAST(fg.`占用订单号` AS CHAR)), '') = ''
  AND COALESCE(TRIM(CAST(src.`占用订单号` AS CHAR)), '') <> '';
"""


RESTORE_FACTORY_PLAN_ORDERS_SQL = r"""
UPDATE {target}.factory_plan fp
JOIN {source}.factory_plan src
  ON src.`合同号` = fp.`合同号`
  AND src.`机型` = fp.`机型`
JOIN {target}.sales_orders so
  ON so.`订单号` = src.`订单号`
SET fp.`订单号` = CAST(src.`订单号` AS CHAR)
WHERE COALESCE(TRIM(CAST(fp.`订单号` AS CHAR)), '') = ''
  AND COALESCE(TRIM(CAST(src.`订单号` AS CHAR)), '') <> '';
"""


RESTORE_FINISHED_GOODS_CONTRACTS_SQL = r"""
UPDATE {target}.finished_goods_data fg
JOIN {target}.factory_plan fp
  ON fp.`订单号` = fg.`占用订单号`
  AND fp.`机型` = fg.`机型`
SET fg.`合同号` = fp.`合同号`
WHERE COALESCE(TRIM(CAST(fg.`合同号` AS CHAR)), '') = ''
  AND COALESCE(TRIM(CAST(fp.`合同号` AS CHAR)), '') <> '';
"""


INSERT_SHIPPING_HISTORY_SQL = r"""
INSERT INTO {target}.shipping_history (
  `批次号`, `机型`, `流水号`, `状态`, `预计入库时间`, `更新时间`, `占用订单号`,
  `客户`, `代理商`, `合同备注`, `合同号`, `archive_month`
)
SELECT
  COALESCE(NULLIF(CAST(fg.`批次号` AS CHAR), ''), CAST(src.`批次号` AS CHAR), ''),
  COALESCE(NULLIF(CAST(fg.`机型` AS CHAR), ''), CAST(src.`机型` AS CHAR), ''),
  CAST(fg.`流水号` AS CHAR),
  '已出库',
  COALESCE(fg.`预计入库时间`, src.`预计入库时间`),
  COALESCE(tl.ship_time, src.`更新时间`, fg.`更新时间`, NOW()),
  COALESCE(NULLIF(CAST(fg.`占用订单号` AS CHAR), ''), CAST(src.`占用订单号` AS CHAR), ''),
  COALESCE(NULLIF(CAST(fg.`客户` AS CHAR), ''), CAST(src.`客户` AS CHAR), CAST(so.`客户名` AS CHAR), ''),
  COALESCE(NULLIF(CAST(fg.`代理商` AS CHAR), ''), CAST(src.`代理商` AS CHAR), CAST(so.`代理商` AS CHAR), ''),
  COALESCE(
    NULLIF(CAST(fg.`合同备注` AS CHAR), ''),
    {source_order_note_expr}
    {source_machine_note_expr}
    CAST(so.`备注` AS CHAR),
    ''
  ),
  COALESCE(NULLIF(CAST(fg.`合同号` AS CHAR), ''), CAST(fp.`合同号` AS CHAR), ''),
  DATE_FORMAT(COALESCE(tl.ship_time, src.`更新时间`, fg.`更新时间`, NOW()), '%Y_%m')
FROM {target}.finished_goods_data fg
LEFT JOIN {source}.finished_goods_data src
  ON src.`流水号` = fg.`流水号`
LEFT JOIN (
  SELECT
    CAST(`流水号` AS CHAR) COLLATE utf8mb4_general_ci AS serial_no,
    MAX(`时间`) AS ship_time
  FROM {target}.transaction_log
  WHERE `操作类型` = '正式发货'
  GROUP BY CAST(`流水号` AS CHAR) COLLATE utf8mb4_general_ci
) tl ON tl.serial_no = CAST(fg.`流水号` AS CHAR) COLLATE utf8mb4_general_ci
LEFT JOIN {target}.sales_orders so
  ON so.`订单号` = COALESCE(NULLIF(fg.`占用订单号`, ''), src.`占用订单号`, '')
LEFT JOIN (
  SELECT
    CAST(`订单号` AS CHAR) COLLATE utf8mb4_general_ci AS order_no,
    CAST(`机型` AS CHAR) COLLATE utf8mb4_general_ci AS model_name,
    MAX(NULLIF(CAST(`合同号` AS CHAR), '')) AS `合同号`
  FROM {target}.factory_plan
  WHERE COALESCE(TRIM(CAST(`订单号` AS CHAR)), '') <> ''
  GROUP BY
    CAST(`订单号` AS CHAR) COLLATE utf8mb4_general_ci,
    CAST(`机型` AS CHAR) COLLATE utf8mb4_general_ci
) fp
  ON fp.order_no = CAST(COALESCE(NULLIF(fg.`占用订单号`, ''), src.`占用订单号`, '') AS CHAR) COLLATE utf8mb4_general_ci
 AND fp.model_name = CAST(fg.`机型` AS CHAR) COLLATE utf8mb4_general_ci
WHERE fg.`状态` = '已出库'
  AND COALESCE(TRIM(CAST(fg.`流水号` AS CHAR)), '') <> ''
  AND NOT EXISTS (
    SELECT 1
    FROM {target}.shipping_history sh
    WHERE CAST(sh.`流水号` AS CHAR) COLLATE utf8mb4_general_ci
        = CAST(fg.`流水号` AS CHAR) COLLATE utf8mb4_general_ci
      AND sh.`状态` = '已出库'
  );
"""


VERIFY_SQL = r"""
SELECT
  (SELECT COUNT(*) FROM {target}.sales_orders) AS sales_orders,
  (SELECT COUNT(*) FROM {target}.finished_goods_data WHERE COALESCE(TRIM(CAST(`占用订单号` AS CHAR)), '') <> '') AS finished_goods_with_order,
  (SELECT COUNT(*) FROM {target}.finished_goods_data WHERE `状态` = '待发货') AS pending_ship_units,
  (SELECT COUNT(*) FROM {target}.finished_goods_data WHERE `状态` = '待发货' AND COALESCE(TRIM(CAST(`占用订单号` AS CHAR)), '') <> '') AS pending_ship_with_order,
  (SELECT COUNT(*) FROM {target}.shipping_history) AS shipping_history_rows,
  (SELECT COUNT(*) FROM {target}.shipping_history WHERE `状态` = '已出库') AS shipped_history_rows,
  (SELECT COUNT(*) FROM {target}.finished_goods_data fg LEFT JOIN {target}.sales_orders so ON so.`订单号` = fg.`占用订单号` WHERE COALESCE(TRIM(CAST(fg.`占用订单号` AS CHAR)), '') <> '' AND so.`订单号` IS NULL) AS orphan_finished_goods_orders;
"""


def db_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name or ""):
        raise ValueError(f"Unsafe database name: {name!r}")
    return f"`{name}`"


def has_column(conn, database: str, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
            """,
            (database, table, column),
        )
        return int(cur.fetchone()["cnt"] or 0) > 0


def build_repair_sql(conn, source_database: str, target_database: str) -> str:
    source = db_ident(source_database)
    target = db_ident(target_database)
    same_db = source_database == target_database

    source_order_note_expr = ""
    source_machine_note_expr = ""
    if has_column(conn, source_database, "finished_goods_data", "订单备注"):
        source_order_note_expr = "NULLIF(CAST(src.`订单备注` AS CHAR), ''),\n    "
    if has_column(conn, source_database, "finished_goods_data", "机台备注/配置"):
        source_machine_note_expr = "NULLIF(CAST(src.`机台备注/配置` AS CHAR), ''),\n    "

    insert_missing_orders_sql = ""
    restore_finished_goods_orders_sql = ""
    restore_factory_plan_orders_sql = ""
    if not same_db:
        insert_missing_orders_sql = INSERT_MISSING_ORDERS_SQL.format(source=source, target=target)
        restore_finished_goods_orders_sql = RESTORE_FINISHED_GOODS_ORDERS_SQL.format(source=source, target=target)
        restore_factory_plan_orders_sql = RESTORE_FACTORY_PLAN_ORDERS_SQL.format(source=source, target=target)

    return REPAIR_SQL.format(
        insert_missing_orders_sql=insert_missing_orders_sql,
        restore_finished_goods_orders_sql=restore_finished_goods_orders_sql,
        restore_factory_plan_orders_sql=restore_factory_plan_orders_sql,
        restore_finished_goods_contracts_sql=RESTORE_FINISHED_GOODS_CONTRACTS_SQL.format(target=target),
        insert_shipping_history_sql=INSERT_SHIPPING_HISTORY_SQL.format(
            source=source,
            target=target,
            source_order_note_expr=source_order_note_expr,
            source_machine_note_expr=source_machine_note_expr,
        ),
    )


def run_backup(args: argparse.Namespace) -> str | None:
    if args.skip_backup:
        return None
    backup_dir = Path(__file__).resolve().parents[1] / "artifacts" / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{args.target_database}_before_shipping_review_repair_{datetime.now():%Y%m%d_%H%M%S}.sql"
    mysqldump = Path(args.mysql_base) / "bin" / "mysqldump.exe"
    subprocess.run(
        [
            str(mysqldump),
            "-uroot",
            f"-p{args.mysql_root_password}",
            "--protocol=tcp",
            "--port=3306",
            "--default-character-set=utf8mb4",
            "--databases",
            args.target_database,
            f"--result-file={backup_path}",
        ],
        check=True,
    )
    return str(backup_path)


def execute_statements(conn, sql: str):
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    rowcounts = []
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
            rowcounts.append({"statement": statement.splitlines()[0][:80], "rowcount": cur.rowcount})
    return rowcounts


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair V7->V8 shipping review data after source SQL import.")
    parser.add_argument("--source-database", required=True)
    parser.add_argument("--target-database", default="rjfinshed")
    parser.add_argument("--mysql-root-password", default="030705")
    parser.add_argument("--mysql-base", default=str(MYSQL_BASE))
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    backup_path = run_backup(args)

    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=args.mysql_root_password,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        sql = build_repair_sql(conn, args.source_database, args.target_database)
        rowcounts = execute_statements(conn, sql)
        with conn.cursor() as cur:
            cur.execute(VERIFY_SQL.format(target=db_ident(args.target_database)))
            verify = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(json.dumps({"backup": backup_path, "rowcounts": rowcounts, "verify": verify}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
