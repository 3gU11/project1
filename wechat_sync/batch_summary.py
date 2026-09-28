from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import pymysql


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
WECHAT_ENV_FILE = Path("C:/RJ_Wechat_App/server/.env")


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _db_config() -> dict[str, Any]:
    env_file = {**_read_env_file(ENV_FILE), **_read_env_file(WECHAT_ENV_FILE)}

    def get(name: str, default: str) -> str:
        value = os.environ.get(name) or env_file.get(name) or ""
        if value.strip().lower() in {"replace_me", "your_password", "你的密码"}:
            value = ""
        return value or default

    database = os.environ.get("MYSQL_DATABASE") or env_file.get("MYSQL_DATABASE") or get("MYSQL_DB", "rjfinshed")

    return {
        "host": get("MYSQL_HOST", "localhost"),
        "port": int(get("MYSQL_PORT", "3306")),
        "user": get("MYSQL_USER", "root"),
        "password": get("MYSQL_PASSWORD", "030705"),
        "database": database,
        "charset": "utf8mb4",
        "autocommit": True,
        "cursorclass": pymysql.cursors.DictCursor,
    }


def connect():
    return pymysql.connect(**_db_config())


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS `wechat_batch_summary` (
      `summary_id` CHAR(32) NOT NULL,
      `batch_no` VARCHAR(100) NOT NULL,
      `expected_inbound_time` DATETIME NULL,
      `model` VARCHAR(100) NOT NULL,
      `quantity` INT NOT NULL DEFAULT 0,
      `批次号` VARCHAR(100) NOT NULL,
      `预计入库时间` DATETIME NULL,
      `机型` VARCHAR(100) NOT NULL,
      `数量` INT NOT NULL DEFAULT 0,
      `更新时间` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`summary_id`),
      INDEX `idx_wechat_batch_summary_batch` (`批次号`),
      INDEX `idx_wechat_batch_summary_inbound` (`预计入库时间`),
      INDEX `idx_wechat_batch_summary_model` (`机型`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_ai`",
    "DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_au`",
    "DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_ad`",
    "DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_group`",
    "DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_all`",
    """
    CREATE PROCEDURE `refresh_wechat_batch_summary_group`(
      IN p_batch_no VARCHAR(100),
      IN p_expected DATETIME,
      IN p_model VARCHAR(100)
    )
    BEGIN
      DECLARE v_batch_no VARCHAR(100);
      DECLARE v_model VARCHAR(100);
      DECLARE v_summary_id CHAR(32);
      DECLARE v_stock_summary_id CHAR(32);

      SET v_batch_no = NULLIF(TRIM(COALESCE(p_batch_no, '')), '');
      SET v_model = NULLIF(TRIM(COALESCE(p_model, '')), '');
      SET v_summary_id = MD5(CONCAT(
        COALESCE(v_batch_no, ''),
        '|',
        COALESCE(DATE_FORMAT(p_expected, '%Y-%m-%d %H:%i:%s'), ''),
        '|',
        COALESCE(v_model, '')
      ));
      SET v_stock_summary_id = MD5(CONCAT('库存中', '|', '', '|', COALESCE(v_model, '')));

      DELETE FROM `wechat_batch_summary`
      WHERE `summary_id` IN (v_summary_id, v_stock_summary_id);

      IF v_batch_no IS NOT NULL AND v_model IS NOT NULL THEN
        INSERT INTO `wechat_batch_summary` (
          `summary_id`,
          `batch_no`,
          `expected_inbound_time`,
          `model`,
          `quantity`,
          `批次号`,
          `预计入库时间`,
          `机型`,
          `数量`
        )
        SELECT
          v_summary_id,
          s.`batch_no`,
          s.`expected_inbound_time`,
          s.`model`,
          s.`quantity`,
          s.`batch_no` AS `批次号`,
          s.`expected_inbound_time` AS `预计入库时间`,
          s.`model` AS `机型`,
          s.`quantity` AS `数量`
        FROM (
          SELECT
            TRIM(`批次号`) AS `batch_no`,
            `预计入库时间` AS `expected_inbound_time`,
            TRIM(`机型`) AS `model`,
            COUNT(*) AS `quantity`
          FROM `finished_goods_data`
          WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') = v_batch_no
            AND `预计入库时间` <=> p_expected
            AND NULLIF(TRIM(COALESCE(`机型`, '')), '') = v_model
            AND TRIM(COALESCE(`状态`, '')) = '待入库'
          GROUP BY TRIM(`批次号`), `预计入库时间`, TRIM(`机型`)
        ) s;
      END IF;

      IF v_model IS NOT NULL THEN
        INSERT INTO `wechat_batch_summary` (
          `summary_id`,
          `batch_no`,
          `expected_inbound_time`,
          `model`,
          `quantity`,
          `批次号`,
          `预计入库时间`,
          `机型`,
          `数量`
        )
        SELECT
          v_stock_summary_id,
          s.`batch_no`,
          s.`expected_inbound_time`,
          s.`model`,
          s.`quantity`,
          s.`batch_no` AS `批次号`,
          s.`expected_inbound_time` AS `预计入库时间`,
          s.`model` AS `机型`,
          s.`quantity` AS `数量`
        FROM (
          SELECT
            '库存中' AS `batch_no`,
            CAST(NULL AS DATETIME) AS `expected_inbound_time`,
            TRIM(`机型`) AS `model`,
            COUNT(*) AS `quantity`
          FROM `finished_goods_data`
          WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') = v_model
            AND TRIM(COALESCE(`状态`, '')) = '库存中'
          GROUP BY TRIM(`机型`)
        ) s;
      END IF;
    END
    """,
    """
    CREATE PROCEDURE `refresh_wechat_batch_summary_all`()
    BEGIN
      TRUNCATE TABLE `wechat_batch_summary`;

      INSERT INTO `wechat_batch_summary` (
        `summary_id`,
        `batch_no`,
        `expected_inbound_time`,
        `model`,
        `quantity`,
        `批次号`,
        `预计入库时间`,
        `机型`,
        `数量`
      )
      SELECT
        MD5(CONCAT(
          s.`batch_no`,
          '|',
          COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
          '|',
          s.`model`
        )) AS `summary_id`,
        s.`batch_no`,
        s.`expected_inbound_time`,
        s.`model`,
        s.`quantity`,
        s.`batch_no` AS `批次号`,
        s.`expected_inbound_time` AS `预计入库时间`,
        s.`model` AS `机型`,
        s.`quantity` AS `数量`
      FROM (
        SELECT
          TRIM(`批次号`) AS `batch_no`,
          `预计入库时间` AS `expected_inbound_time`,
          TRIM(`机型`) AS `model`,
          COUNT(*) AS `quantity`
        FROM `finished_goods_data`
        WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
          AND TRIM(COALESCE(`状态`, '')) = '待入库'
        GROUP BY TRIM(`批次号`), `预计入库时间`, TRIM(`机型`)
        UNION ALL
        SELECT
          '库存中' AS `batch_no`,
          CAST(NULL AS DATETIME) AS `expected_inbound_time`,
          TRIM(`机型`) AS `model`,
          COUNT(*) AS `quantity`
        FROM `finished_goods_data`
        WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
          AND TRIM(COALESCE(`状态`, '')) = '库存中'
        GROUP BY TRIM(`机型`)
      ) s;
    END
    """,
    """
    CREATE TRIGGER `trg_fg_wechat_summary_ai`
    AFTER INSERT ON `finished_goods_data`
    FOR EACH ROW
    BEGIN
      CALL `refresh_wechat_batch_summary_group`(NEW.`批次号`, NEW.`预计入库时间`, NEW.`机型`);
    END
    """,
    """
    CREATE TRIGGER `trg_fg_wechat_summary_au`
    AFTER UPDATE ON `finished_goods_data`
    FOR EACH ROW
    BEGIN
      CALL `refresh_wechat_batch_summary_group`(OLD.`批次号`, OLD.`预计入库时间`, OLD.`机型`);
      IF NOT (
        OLD.`批次号` <=> NEW.`批次号`
        AND OLD.`预计入库时间` <=> NEW.`预计入库时间`
        AND OLD.`机型` <=> NEW.`机型`
      ) THEN
        CALL `refresh_wechat_batch_summary_group`(NEW.`批次号`, NEW.`预计入库时间`, NEW.`机型`);
      END IF;
    END
    """,
    """
    CREATE TRIGGER `trg_fg_wechat_summary_ad`
    AFTER DELETE ON `finished_goods_data`
    FOR EACH ROW
    BEGIN
      CALL `refresh_wechat_batch_summary_group`(OLD.`批次号`, OLD.`预计入库时间`, OLD.`机型`);
    END
    """,
]


def install() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in DDL_STATEMENTS:
                cur.execute(statement)
            cur.execute("CALL `refresh_wechat_batch_summary_all`()")


def refresh() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL `refresh_wechat_batch_summary_all`()")


def list_rows(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT `批次号`, `预计入库时间`, `机型`, `数量`, `更新时间`
                FROM `wechat_batch_summary`
                ORDER BY `预计入库时间` DESC, `批次号` DESC, `机型` ASC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cur.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the WeChat batch summary table.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install", help="Create table, procedures, triggers, and initial data.")
    sub.add_parser("refresh", help="Rebuild the summary table from finished_goods_data.")
    list_parser = sub.add_parser("list", help="Print recent summary rows.")
    list_parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if args.command == "install":
        install()
        print("wechat_batch_summary installed and refreshed.")
    elif args.command == "refresh":
        refresh()
        print("wechat_batch_summary refreshed.")
    elif args.command == "list":
        for row in list_rows(args.limit):
            print(row)


if __name__ == "__main__":
    main()
