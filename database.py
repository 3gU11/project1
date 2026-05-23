from functools import lru_cache
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from config import (
    MYSQL_DB,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    DEFAULT_ROLE_PERMISSIONS,
    DEFAULT_USERS,
)


def get_schema_rollback_sql():
    return [
        "ALTER TABLE role_permissions DROP FOREIGN KEY fk_role_permissions_role",
        "ALTER TABLE users DROP FOREIGN KEY fk_users_role",
        "DROP INDEX uq_role_permissions_role_func ON role_permissions",
        "DROP INDEX idx_fg_status_model_order ON finished_goods_data",
        "DROP INDEX idx_fg_batch_status ON finished_goods_data",
        "DROP INDEX idx_fg_updated_at ON finished_goods_data",
        "DROP INDEX idx_orders_status_time ON sales_orders",
        "DROP INDEX idx_orders_delivery ON sales_orders",
        "DROP INDEX idx_fp_contract_status_due ON factory_plan",
        "DROP INDEX idx_fp_due_date ON factory_plan",
        "DROP INDEX idx_log_time ON transaction_log",
        "DROP INDEX idx_sys_operation_log_time ON sys_operation_log",
        "DROP INDEX idx_sys_operation_log_user ON sys_operation_log",
        "DROP INDEX idx_sys_operation_log_module ON sys_operation_log",
        "DROP INDEX idx_import_batch_model ON plan_import",
        "DROP INDEX idx_ship_month_time ON shipping_history",
        "DROP INDEX idx_rush_order_queue_status ON rush_order_queue",
        "DROP INDEX idx_rush_order_queue_contract ON rush_order_queue",
        "DROP INDEX uq_contract_path ON contract_records",
        "DROP TABLE IF EXISTS rush_order_queue",
        "DROP TABLE IF EXISTS sys_operation_log",
        "DROP TABLE IF EXISTS roles",
    ]


@lru_cache(maxsize=1)
def get_engine():
    """返回全局复用的 SQLAlchemy Engine。"""
    url = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
        f"?charset=utf8mb4"
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={
            "auth_plugin_map": {
                "caching_sha2_password": "mysql_native_password",
                "sha256_password": "mysql_native_password"
            },
            "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_general_ci"
        },
    )


def init_mysql_tables():
    """首次运行时建表，并写入默认用户（幂等操作，可安全重复调用）"""
    engine = get_engine()
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS finished_goods_data (
            `流水号`        VARCHAR(100) NOT NULL,
            `批次号`        VARCHAR(100) DEFAULT '',
            `机型`          VARCHAR(100) DEFAULT '',
            `状态`          VARCHAR(50)  DEFAULT '',
            `预计入库时间`  DATETIME NULL,
            `更新时间`      TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            `占用订单号`    VARCHAR(100) NULL,
            `客户`          VARCHAR(200) DEFAULT '',
            `代理商`        VARCHAR(200) DEFAULT '',
            `合同备注`      TEXT,
            `Location_Code` VARCHAR(100) DEFAULT '',
            `合同号`        VARCHAR(100) DEFAULT '',
            PRIMARY KEY (`流水号`),
            INDEX `idx_fg_order` (`占用订单号`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS sales_orders (
            `订单号`        VARCHAR(100) NOT NULL,
            `客户名`        VARCHAR(200) DEFAULT '',
            `代理商`        VARCHAR(200) DEFAULT '',
            `需求机型`      TEXT,
            `需求数量`      INT DEFAULT 0,
            `下单时间`      DATETIME NULL,
            `备注`          TEXT,
            `包装选项`      VARCHAR(100) DEFAULT '',
            `发货时间`      DATETIME NULL,
            `指定批次/来源` JSON NULL,
            `status`        VARCHAR(50)  DEFAULT 'active',
            `delete_reason` TEXT,
            PRIMARY KEY (`订单号`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS factory_plan (
            `id`            INT NOT NULL AUTO_INCREMENT,
            `合同号`        VARCHAR(100) DEFAULT '',
            `机型`          VARCHAR(100) DEFAULT '',
            `排产数量`      VARCHAR(20)  DEFAULT '',
            `要求交期`      VARCHAR(50)  DEFAULT '',
            `状态`          VARCHAR(50)  DEFAULT '',
            `备注`          TEXT,
            `客户名`        VARCHAR(200) DEFAULT '',
            `代理商`        VARCHAR(200) DEFAULT '',
            `指定批次/来源` JSON NULL,
            `订单号`        VARCHAR(100) NULL,
            PRIMARY KEY (`id`),
            INDEX `idx_fp_order` (`订单号`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS transaction_log (
            `id`        INT NOT NULL AUTO_INCREMENT,
            `时间`      DATETIME NULL,
            `操作类型`  VARCHAR(200) DEFAULT '',
            `流水号`    VARCHAR(100) DEFAULT '',
            `操作员`    VARCHAR(100) DEFAULT '',
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS planning_records (
            `id`         INT NOT NULL AUTO_INCREMENT,
            `order_id`   VARCHAR(100) DEFAULT '',
            `model`      VARCHAR(100) DEFAULT '',
            `plan_info`  TEXT,
            `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_order_model` (`order_id`, `model`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS contract_records (
            `id`          INT NOT NULL AUTO_INCREMENT,
            `contract_id` VARCHAR(100) DEFAULT '',
            `customer`    VARCHAR(200) DEFAULT '',
            `file_name`   VARCHAR(500) DEFAULT '',
            `file_path`   VARCHAR(1000) DEFAULT '',
            `file_hash`   VARCHAR(64)  DEFAULT '',
            `uploader`    VARCHAR(100) DEFAULT '',
            `upload_time` DATETIME NULL,
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            `id`        INT NOT NULL AUTO_INCREMENT,
            `timestamp` DATETIME NULL,
            `user`      VARCHAR(100) DEFAULT '',
            `ip`        VARCHAR(100) DEFAULT '',
            `action`    VARCHAR(200) DEFAULT '',
            `details`   TEXT,
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS sys_operation_log (
            `id`           BIGINT NOT NULL AUTO_INCREMENT,
            `user_id`      VARCHAR(100) DEFAULT '',
            `username`     VARCHAR(100) DEFAULT '',
            `operate_time` DATETIME NULL,
            `module`       VARCHAR(100) DEFAULT '',
            `action_type`  VARCHAR(100) DEFAULT '',
            `biz_type`     VARCHAR(100) DEFAULT '',
            `content`      TEXT,
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            `username`      VARCHAR(100) NOT NULL,
            `password`      VARCHAR(200) DEFAULT '',
            `role`          VARCHAR(50)  DEFAULT '',
            `name`          VARCHAR(100) DEFAULT '',
            `status`        VARCHAR(50)  DEFAULT 'pending',
            `register_time` DATETIME NULL,
            `audit_time`    DATETIME NULL,
            `auditor`       VARCHAR(100) DEFAULT '',
            PRIMARY KEY (`username`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            `id`         BIGINT NOT NULL AUTO_INCREMENT,
            `username`   VARCHAR(100) NOT NULL,
            `token_hash` VARCHAR(128) NOT NULL,
            `expires_at` DATETIME NOT NULL,
            `revoked`    TINYINT(1) NOT NULL DEFAULT 0,
            `created_at` DATETIME NULL,
            `revoked_at` DATETIME NULL,
            PRIMARY KEY (`id`),
            INDEX `idx_user_sessions_username` (`username`),
            UNIQUE KEY `uq_user_sessions_token_hash` (`token_hash`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
            `id`        INT NOT NULL AUTO_INCREMENT,
            `role_id`   VARCHAR(50)  DEFAULT '',
            `func_code` VARCHAR(100) DEFAULT '',
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS shipping_history (
            `id`            INT NOT NULL AUTO_INCREMENT,
            `批次号`        VARCHAR(100) DEFAULT '',
            `机型`          VARCHAR(100) DEFAULT '',
            `流水号`        VARCHAR(100) DEFAULT '',
            `状态`          VARCHAR(50)  DEFAULT '',
            `预计入库时间`  DATETIME NULL,
            `更新时间`      DATETIME NULL,
            `占用订单号`    VARCHAR(100) DEFAULT '',
            `客户`          VARCHAR(200) DEFAULT '',
            `代理商`        VARCHAR(200) DEFAULT '',
            `合同备注`      TEXT,
            `合同号`        VARCHAR(100) DEFAULT '',
            `archive_month` VARCHAR(20)  DEFAULT '',
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS plan_import (
            `流水号`        VARCHAR(100) NOT NULL,
            `批次号`        VARCHAR(100) DEFAULT '',
            `机型`          VARCHAR(100) DEFAULT '',
            `状态`          VARCHAR(50)  DEFAULT '待入库',
            `预计入库时间`  DATETIME NULL,
            `客户`          VARCHAR(200) DEFAULT '',
            `代理商`        VARCHAR(200) DEFAULT '',
            `合同备注`      TEXT,
            `合同号`        VARCHAR(100) DEFAULT '',
            `订单号`        VARCHAR(100) DEFAULT '',
            PRIMARY KEY (`流水号`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS warehouse_layout (
            `layout_id`    VARCHAR(100) NOT NULL,
            `layout_json`  LONGTEXT,
            `update_time`  DATETIME NULL,
            PRIMARY KEY (`layout_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS model_dictionary (
            `id`         INT NOT NULL AUTO_INCREMENT,
            `model_name` VARCHAR(100) NOT NULL,
            `model_family` VARCHAR(32) NULL,
            `sort_order` INT NOT NULL DEFAULT 0,
            `enabled`    TINYINT(1) NOT NULL DEFAULT 1,
            `remark`     VARCHAR(255) DEFAULT '',
            `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_model_dictionary_name` (`model_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS rush_order_queue (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `contract_no` VARCHAR(100) NOT NULL,
            `customer` VARCHAR(200) DEFAULT '',
            `dealer_name` VARCHAR(200) DEFAULT '',
            `model_type` VARCHAR(100) NOT NULL,
            `due_date` DATE NULL,
            `remark` TEXT NULL,
            `source` VARCHAR(50) NOT NULL DEFAULT 'contract',
            `status` VARCHAR(30) NOT NULL DEFAULT 'pending',
            `created_by` VARCHAR(100) DEFAULT '',
            `updated_by` VARCHAR(100) DEFAULT '',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            INDEX `idx_rush_order_queue_status` (`status`, `created_at`),
            INDEX `idx_rush_order_queue_contract` (`contract_no`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dealer_orders (
          id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
          order_no VARCHAR(64) NOT NULL,
          line_no INT NOT NULL DEFAULT 1,
          dealer_id VARCHAR(128) NOT NULL,
          dealer_name VARCHAR(255) NOT NULL,
          dealer_phone VARCHAR(64) DEFAULT '',
          customer_name VARCHAR(255) NOT NULL,
          contact_name VARCHAR(128) NOT NULL,
          contact_phone VARCHAR(64) NOT NULL,
          model VARCHAR(255) NOT NULL,
          batch_no VARCHAR(255) DEFAULT '',
          eta VARCHAR(64) DEFAULT '',
          inventory_type VARCHAR(32) DEFAULT '',
          quantity INT NOT NULL DEFAULT 1,
          approved_qty INT NOT NULL DEFAULT 0,
          allocated_qty INT NOT NULL DEFAULT 0,
          delivery_date VARCHAR(64) DEFAULT '',
          remark TEXT,
          extra_remark TEXT,
          ERMQ INT NOT NULL DEFAULT 0,
          factory_pending TINYINT(1) NOT NULL DEFAULT 0,
          source VARCHAR(32) NOT NULL DEFAULT 'wechat',
          last_synced_at DATETIME NULL,
          sync_status VARCHAR(32) NOT NULL DEFAULT 'pending',
          sync_error TEXT,
          factory_reviewed_at DATETIME NULL,
          factory_reviewed_by VARCHAR(128) DEFAULT '',
          extra_remark_reviewed_at DATETIME NULL,
          extra_remark_reviewed_by VARCHAR(128) DEFAULT '',
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          reviewed_at DATETIME NULL,
          reviewed_by VARCHAR(128) DEFAULT '',
          contract_no VARCHAR(128) DEFAULT '',
          v7_order_no VARCHAR(128) DEFAULT '',
          review_note TEXT,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uq_dealer_order_line (order_no, line_no),
          INDEX idx_dealer_order_no (order_no),
          INDEX idx_dealer_id (dealer_id),
          INDEX idx_status (status),
          INDEX idx_batch_model_status (batch_no, model, status),
          INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dealer_order_sync_events (
          id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
          event_id VARCHAR(64) NOT NULL UNIQUE,
          order_no VARCHAR(64) NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          source VARCHAR(32) NOT NULL DEFAULT 'wechat',
          payload_json JSON NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          attempts INT NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          acked_at DATETIME NULL,
          INDEX idx_sync_events_order (order_no),
          INDEX idx_sync_events_status (status, id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS wechat_batch_summary (
          summary_id CHAR(32) NOT NULL,
          batch_no VARCHAR(100) NOT NULL,
          expected_inbound_time DATETIME NULL,
          model VARCHAR(100) NOT NULL,
          quantity INT NOT NULL DEFAULT 0,
          批次号 VARCHAR(100) NOT NULL,
          预计入库时间 DATETIME NULL,
          机型 VARCHAR(100) NOT NULL,
          数量 INT NOT NULL DEFAULT 0,
          更新时间 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (summary_id),
          INDEX idx_wbs_batch (批次号),
          INDEX idx_wbs_inbound (预计入库时间),
          INDEX idx_wbs_model (机型)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]
    with engine.begin() as conn:
        def _index_exists(table_name, index_name):
            return conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND INDEX_NAME=:i"
            ), {"db": MYSQL_DB, "t": table_name, "i": index_name}).scalar() > 0

        def _constraint_exists(table_name, constraint_name):
            return conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND CONSTRAINT_NAME=:c"
            ), {"db": MYSQL_DB, "t": table_name, "c": constraint_name}).scalar() > 0

        def _column_exists(table_name, column_name):
            return conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND COLUMN_NAME=:c"
            ), {"db": MYSQL_DB, "t": table_name, "c": column_name}).scalar() > 0

        def _add_index_if_missing(table_name, index_name, columns_sql, unique=False):
            if not _index_exists(table_name, index_name):
                index_type = "UNIQUE INDEX" if unique else "INDEX"
                conn.execute(text(
                    f"ALTER TABLE `{table_name}` ADD {index_type} `{index_name}` ({columns_sql})"
                ))

        def _drop_fk_if_exists(table_name, fk_name):
            if _constraint_exists(table_name, fk_name):
                conn.execute(text(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{fk_name}`"))

        def _to_int_qty(value):
            try:
                return int(float(value))
            except Exception:
                return 0

        def _parse_alloc(content):
            if isinstance(content, dict):
                return {str(k): _to_int_qty(v) for k, v in content.items() if _to_int_qty(v) > 0}
            raw = str(content or "").strip()
            if not raw:
                return {}
            payload = raw
            if ":" in raw and not raw.startswith("{"):
                payload = raw.split(":", 1)[1].strip()
            for candidate in (payload, payload.replace("'", '"')):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return {str(k): _to_int_qty(v) for k, v in parsed.items() if _to_int_qty(v) > 0}
                except Exception:
                    continue
            return {}

        def _parse_plan_map(content):
            if isinstance(content, dict):
                normalized = {}
                for k, v in content.items():
                    alloc = _parse_alloc(v)
                    if alloc:
                        normalized[str(k)] = alloc
                return normalized
            raw = str(content or "").strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    normalized = {}
                    for k, v in parsed.items():
                        alloc = _parse_alloc(v)
                        if alloc:
                            normalized[str(k)] = alloc
                    return normalized
            except Exception:
                pass
            merged = {}
            for part in raw.split(";"):
                if ":" not in part:
                    continue
                model, alloc_raw = part.split(":", 1)
                model = model.strip()
                alloc = _parse_alloc(alloc_raw.strip())
                if not model or not alloc:
                    continue
                if model not in merged:
                    merged[model] = {}
                for b, q in alloc.items():
                    merged[model][b] = merged[model].get(b, 0) + q
            return merged

        for ddl in ddl_statements:
            conn.execute(text(ddl))

        for col_name, col_def in [
            ("extra_remark", "TEXT AFTER `remark`"),
            ("ERMQ", "INT NOT NULL DEFAULT 0 AFTER `extra_remark`"),
            ("factory_pending", "TINYINT(1) NOT NULL DEFAULT 0 AFTER `ERMQ`"),
            ("source", "VARCHAR(32) NOT NULL DEFAULT 'wechat' AFTER `factory_pending`"),
            ("last_synced_at", "DATETIME NULL AFTER `source`"),
            ("sync_status", "VARCHAR(32) NOT NULL DEFAULT 'pending' AFTER `last_synced_at`"),
            ("sync_error", "TEXT AFTER `sync_status`"),
            ("factory_reviewed_at", "DATETIME NULL AFTER `sync_error`"),
            ("factory_reviewed_by", "VARCHAR(128) DEFAULT '' AFTER `factory_reviewed_at`"),
            ("extra_remark_reviewed_at", "DATETIME NULL AFTER `factory_reviewed_by`"),
            ("extra_remark_reviewed_by", "VARCHAR(128) DEFAULT '' AFTER `extra_remark_reviewed_at`"),
        ]:
            if not _column_exists("dealer_orders", col_name):
                try:
                    conn.execute(text(f"ALTER TABLE dealer_orders ADD COLUMN `{col_name}` {col_def}"))
                except Exception:
                    pass

        if not _column_exists("model_dictionary", "model_family"):
            conn.execute(text(
                "ALTER TABLE model_dictionary "
                "ADD COLUMN `model_family` VARCHAR(32) NULL AFTER `model_name`"
            ))
        for old_family, new_family in {
            "小机G": "中小型G",
            "小机XS": "中小型XS",
            "小机/XS": "中小型XS",
            "小机AUTO": "中小型AUTO",
            "大机XS": "中大型XS",
            "大机AUTO": "中大型AUTO",
            "SPECIAL": "特殊",
        }.items():
            conn.execute(
                text(
                    "UPDATE model_dictionary "
                    "SET `model_family`=:new_family "
                    "WHERE TRIM(COALESCE(`model_family`, ''))=:old_family"
                ),
                {"old_family": old_family, "new_family": new_family},
            )

        try:
            if not _column_exists("sales_orders", "包装选项"):
                conn.execute(text(
                    "ALTER TABLE sales_orders "
                    "ADD COLUMN `包装选项` VARCHAR(100) "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '' AFTER `备注`"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE sales_orders "
                    "MODIFY COLUMN `包装选项` VARCHAR(100) "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT ''"
                ))
        except Exception:
            pass

        conn.execute(text("UPDATE finished_goods_data SET `占用订单号`=NULL WHERE `占用订单号`=''"))
        conn.execute(text("UPDATE factory_plan SET `订单号`=NULL WHERE `订单号`=''"))
        conn.execute(text(
            "UPDATE finished_goods_data fg LEFT JOIN sales_orders so ON fg.`占用订单号`=so.`订单号` "
            "SET fg.`占用订单号`=NULL WHERE fg.`占用订单号` IS NOT NULL AND so.`订单号` IS NULL"
        ))
        conn.execute(text(
            "UPDATE factory_plan fp LEFT JOIN sales_orders so ON fp.`订单号`=so.`订单号` "
            "SET fp.`订单号`=NULL WHERE fp.`订单号` IS NOT NULL AND so.`订单号` IS NULL"
        ))
        # Normalize legacy/invalid factory_plan status into 待规划.
        conn.execute(text("UPDATE factory_plan SET `状态`='待规划' WHERE TRIM(COALESCE(`状态`, ''))='未下单'"))
        conn.execute(text("UPDATE factory_plan SET `状态`='待规划' WHERE TRIM(COALESCE(`状态`, ''))=''"))
        conn.execute(text(
            "UPDATE factory_plan SET `状态`='已转订单' "
            "WHERE TRIM(COALESCE(`状态`, ''))='已规划' "
            "AND COALESCE(TRIM(`订单号`), '') <> ''"
        ))
        conn.execute(text("UPDATE sales_orders SET `需求数量`=0 WHERE `需求数量` IS NULL OR `需求数量`=''"))

        date_columns = [
            ("finished_goods_data", "预计入库时间"),
            ("finished_goods_data", "更新时间"),
            ("sales_orders", "下单时间"),
            ("sales_orders", "发货时间"),
            ("transaction_log", "时间"),
            ("planning_records", "updated_at"),
            ("contract_records", "upload_time"),
            ("audit_log", "timestamp"),
            ("sys_operation_log", "operate_time"),
            ("users", "register_time"),
            ("users", "audit_time"),
            ("shipping_history", "预计入库时间"),
            ("shipping_history", "更新时间"),
            ("plan_import", "预计入库时间"),
        ]
        for table_name, col_name in date_columns:
            try:
                # 只在列类型是VARCHAR/TEXT时处理空字符串，否则可能会因为严格模式报错
                conn.execute(text(f"UPDATE `{table_name}` SET `{col_name}`=NULL WHERE `{col_name}`=''"))
            except Exception:
                pass

        sales_rows = conn.execute(text("SELECT `订单号`, `指定批次/来源` FROM sales_orders")).fetchall()
        for order_id, source_val in sales_rows:
            normalized = _parse_plan_map(source_val)
            conn.execute(
                text("UPDATE sales_orders SET `指定批次/来源`=:v WHERE `订单号`=:oid"),
                {"v": json.dumps(normalized, ensure_ascii=False), "oid": order_id},
            )

        try:
            result = conn.execute(text("SHOW COLUMNS FROM factory_plan LIKE 'id'"))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE factory_plan ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST"))
        except Exception:
            pass

        try:
            plan_rows = conn.execute(text("SELECT `id`, `指定批次/来源` FROM factory_plan")).fetchall()
            for row_id, source_val in plan_rows:
                normalized = _parse_alloc(source_val)
                conn.execute(
                    text("UPDATE factory_plan SET `指定批次/来源`=:v WHERE `id`=:rid"),
                    {"v": json.dumps(normalized, ensure_ascii=False), "rid": row_id},
                )
        except Exception:
            pass

        migration_sql = [
            "ALTER TABLE finished_goods_data MODIFY COLUMN `预计入库时间` DATETIME NULL",
            "ALTER TABLE finished_goods_data MODIFY COLUMN `更新时间` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
            "ALTER TABLE finished_goods_data MODIFY COLUMN `占用订单号` VARCHAR(100) NULL",
            "ALTER TABLE sales_orders MODIFY COLUMN `需求数量` INT DEFAULT 0",
            "ALTER TABLE sales_orders MODIFY COLUMN `下单时间` DATETIME NULL",
            "ALTER TABLE sales_orders MODIFY COLUMN `发货时间` DATETIME NULL",
            "ALTER TABLE sales_orders MODIFY COLUMN `指定批次/来源` JSON NULL",
            "ALTER TABLE factory_plan MODIFY COLUMN `指定批次/来源` JSON NULL",
            "ALTER TABLE factory_plan MODIFY COLUMN `订单号` VARCHAR(100) NULL",
            "ALTER TABLE transaction_log MODIFY COLUMN `时间` DATETIME NULL",
            "ALTER TABLE planning_records MODIFY COLUMN `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
            "ALTER TABLE contract_records MODIFY COLUMN `upload_time` DATETIME NULL",
            "ALTER TABLE audit_log MODIFY COLUMN `timestamp` DATETIME NULL",
            "ALTER TABLE sys_operation_log MODIFY COLUMN `operate_time` DATETIME NULL",
            "ALTER TABLE users MODIFY COLUMN `register_time` DATETIME NULL",
            "ALTER TABLE users MODIFY COLUMN `audit_time` DATETIME NULL",
            "ALTER TABLE shipping_history MODIFY COLUMN `预计入库时间` DATETIME NULL",
            "ALTER TABLE shipping_history MODIFY COLUMN `更新时间` DATETIME NULL",
            "ALTER TABLE plan_import MODIFY COLUMN `预计入库时间` DATETIME NULL",
        ]
        for sql in migration_sql:
            try:
                conn.execute(text(sql))
            except Exception:
                pass

        # plan_import: add 客户/代理商/合同备注, drop 机台备注/配置
        for col_name, col_def in [
            ("客户", "VARCHAR(200) DEFAULT '' AFTER `预计入库时间`"),
            ("代理商", "VARCHAR(200) DEFAULT '' AFTER `客户`"),
            ("合同备注", "TEXT AFTER `代理商`"),
            ("合同号", "VARCHAR(100) DEFAULT '' AFTER `合同备注`"),
            ("订单号", "VARCHAR(100) DEFAULT '' AFTER `合同号`"),
        ]:
            if not _column_exists("plan_import", col_name):
                try:
                    conn.execute(text(f"ALTER TABLE plan_import ADD COLUMN `{col_name}` {col_def}"))
                except Exception:
                    pass
        if _column_exists("plan_import", "机台备注/配置"):
            try:
                conn.execute(text("ALTER TABLE plan_import DROP COLUMN `机台备注/配置`"))
            except Exception:
                pass

        for table_name, after_col in [
            ("finished_goods_data", "代理商"),
            ("shipping_history", "代理商"),
        ]:
            if not _column_exists(table_name, "合同备注"):
                try:
                    conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `合同备注` TEXT AFTER `{after_col}`"))
                except Exception:
                    pass
            for legacy_col in ["订单备注", "机台备注/配置"]:
                if _column_exists(table_name, legacy_col):
                    try:
                        conn.execute(text(f"""
                            UPDATE `{table_name}`
                            SET `合同备注` = `{legacy_col}`
                            WHERE COALESCE(TRIM(`合同备注`), '') = ''
                              AND COALESCE(TRIM(`{legacy_col}`), '') <> ''
                        """))
                    except Exception:
                        pass
                    try:
                        conn.execute(text(f"ALTER TABLE `{table_name}` DROP COLUMN `{legacy_col}`"))
                    except Exception:
                        pass

        try:
            fk_fg = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=:db AND TABLE_NAME='finished_goods_data' "
                "AND CONSTRAINT_NAME='fk_finished_goods_order'"
            ), {"db": MYSQL_DB}).scalar()
            if fk_fg == 0:
                conn.execute(text(
                    "ALTER TABLE finished_goods_data "
                    "ADD CONSTRAINT fk_finished_goods_order "
                    "FOREIGN KEY (`占用订单号`) REFERENCES sales_orders(`订单号`) "
                    "ON UPDATE CASCADE ON DELETE SET NULL"
                ))
        except Exception:
            pass

        try:
            fk_fp = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=:db AND TABLE_NAME='factory_plan' "
                "AND CONSTRAINT_NAME='fk_factory_plan_order'"
            ), {"db": MYSQL_DB}).scalar()
            if fk_fp == 0:
                conn.execute(text(
                    "ALTER TABLE factory_plan "
                    "ADD CONSTRAINT fk_factory_plan_order "
                    "FOREIGN KEY (`订单号`) REFERENCES sales_orders(`订单号`) "
                    "ON UPDATE CASCADE ON DELETE SET NULL"
                ))
        except Exception:
            pass

        try:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS roles ("
                "`role_id` VARCHAR(50) NOT NULL,"
                "`role_name` VARCHAR(100) DEFAULT '',"
                "PRIMARY KEY (`role_id`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            ))
        except Exception:
            pass

        known_roles = {}
        for _, info in DEFAULT_USERS.items():
            role_id = str(info.get("role", "")).strip()
            if role_id:
                known_roles[role_id] = role_id
        for role_id in DEFAULT_ROLE_PERMISSIONS.keys():
            rid = str(role_id).strip()
            if rid:
                known_roles[rid] = rid

        for role_id, role_name in known_roles.items():
            conn.execute(
                text("INSERT IGNORE INTO roles (role_id, role_name) VALUES (:rid, :rname)"),
                {"rid": role_id, "rname": role_name},
            )

        try:
            role_values = conn.execute(text("SELECT DISTINCT role FROM users WHERE TRIM(COALESCE(role, '')) <> ''")).fetchall()
            for (role_id,) in role_values:
                rid = str(role_id).strip()
                conn.execute(
                    text("INSERT IGNORE INTO roles (role_id, role_name) VALUES (:rid, :rname)"),
                    {"rid": rid, "rname": rid},
                )
        except Exception:
            pass

        try:
            role_values_perm = conn.execute(text("SELECT DISTINCT role_id FROM role_permissions WHERE TRIM(COALESCE(role_id, '')) <> ''")).fetchall()
            for (role_id,) in role_values_perm:
                rid = str(role_id).strip()
                conn.execute(
                    text("INSERT IGNORE INTO roles (role_id, role_name) VALUES (:rid, :rname)"),
                    {"rid": rid, "rname": rid},
                )
        except Exception:
            pass

        try:
            conn.execute(text(
                "DELETE rp1 FROM role_permissions rp1 "
                "INNER JOIN role_permissions rp2 "
                "ON rp1.role_id=rp2.role_id AND rp1.func_code=rp2.func_code AND rp1.id > rp2.id"
            ))
            conn.execute(text("DELETE FROM role_permissions WHERE TRIM(COALESCE(role_id, ''))='' OR TRIM(COALESCE(func_code, ''))=''"))
        except Exception:
            pass

        _add_index_if_missing("role_permissions", "uq_role_permissions_role_func", "`role_id`, `func_code`", unique=True)

        try:
            conn.execute(text(
                "DELETE c1 FROM contract_records c1 "
                "INNER JOIN contract_records c2 "
                "ON c1.contract_id=c2.contract_id AND c1.file_path=c2.file_path AND c1.id > c2.id "
                "WHERE TRIM(COALESCE(c1.file_path, '')) <> ''"
            ))
            _add_index_if_missing("contract_records", "uq_contract_path", "`contract_id`, `file_path`(255)", unique=True)
        except Exception:
            pass

        _add_index_if_missing("finished_goods_data", "idx_fg_status_model_order", "`状态`, `机型`, `占用订单号`")
        _add_index_if_missing("finished_goods_data", "idx_fg_status_model", "`状态`, `机型`")
        _add_index_if_missing("finished_goods_data", "idx_fg_status_location", "`状态`, `Location_Code`")
        _add_index_if_missing("finished_goods_data", "idx_fg_batch_status", "`批次号`, `状态`")
        _add_index_if_missing("finished_goods_data", "idx_fg_updated_at", "`更新时间`")
        _add_index_if_missing("sales_orders", "idx_orders_status_time", "`status`, `下单时间`")
        _add_index_if_missing("sales_orders", "idx_orders_customer", "`客户名`")
        _add_index_if_missing("sales_orders", "idx_orders_customer_time", "`客户名`, `下单时间`")
        _add_index_if_missing("sales_orders", "idx_orders_delivery", "`发货时间`")
        _add_index_if_missing("factory_plan", "idx_fp_contract_status_due", "`合同号`, `状态`, `要求交期`")
        _add_index_if_missing("factory_plan", "idx_fp_due_date", "`要求交期`")
        _add_index_if_missing("transaction_log", "idx_log_time", "`时间`")
        _add_index_if_missing("sys_operation_log", "idx_sys_operation_log_time", "`operate_time`")
        _add_index_if_missing("sys_operation_log", "idx_sys_operation_log_user", "`user_id`, `operate_time`")
        _add_index_if_missing("sys_operation_log", "idx_sys_operation_log_module", "`module`, `action_type`, `biz_type`")
        _add_index_if_missing("contract_records", "idx_contract_id", "`contract_id`")
        _add_index_if_missing("contract_records", "idx_contract_upload_time", "`upload_time`")
        _add_index_if_missing("plan_import", "idx_import_batch_model", "`批次号`, `机型`")
        _add_index_if_missing("shipping_history", "idx_ship_month_time", "`archive_month`, `更新时间`")

        _drop_fk_if_exists("users", "fk_users_role")
        _drop_fk_if_exists("role_permissions", "fk_role_permissions_role")

        if not _constraint_exists("users", "fk_users_role"):
            try:
                conn.execute(text(
                    "ALTER TABLE users "
                    "ADD CONSTRAINT fk_users_role "
                    "FOREIGN KEY (`role`) REFERENCES roles(`role_id`) "
                    "ON UPDATE CASCADE ON DELETE RESTRICT"
                ))
            except Exception:
                pass

        if not _constraint_exists("role_permissions", "fk_role_permissions_role"):
            try:
                conn.execute(text(
                    "ALTER TABLE role_permissions "
                    "ADD CONSTRAINT fk_role_permissions_role "
                    "FOREIGN KEY (`role_id`) REFERENCES roles(`role_id`) "
                    "ON UPDATE CASCADE ON DELETE CASCADE"
                ))
            except Exception:
                pass

        result = conn.execute(text("SHOW COLUMNS FROM finished_goods_data LIKE 'Location_Code'"))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `Location_Code` VARCHAR(100) DEFAULT ''"))
        if not _column_exists("finished_goods_data", "合同号"):
            conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `合同号` VARCHAR(100) DEFAULT '' AFTER `Location_Code`"))
        if not _column_exists("shipping_history", "合同号"):
            conn.execute(text("ALTER TABLE shipping_history ADD COLUMN `合同号` VARCHAR(100) DEFAULT '' AFTER `合同备注`"))

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for uid, info in DEFAULT_USERS.items():
            conn.execute(text(
                "INSERT IGNORE INTO users "
                "(username, password, role, name, status, register_time, audit_time, auditor) "
                "VALUES (:u, :p, :r, :n, 'active', :t, :t, 'System')"
            ), {"u": uid, "p": info["password"], "r": info["role"], "n": info["name"], "t": current_time})

        result = conn.execute(text("SELECT COUNT(*) FROM role_permissions"))
        if result.fetchone()[0] == 0:
            for role_id, func_codes in DEFAULT_ROLE_PERMISSIONS.items():
                for func_code in func_codes:
                    conn.execute(
                        text("INSERT IGNORE INTO role_permissions (role_id, func_code) VALUES (:r, :f)"),
                        {"r": role_id, "f": func_code},
                    )


# Schema 版本控制常量
CURRENT_SCHEMA_VERSION = 9


def _ensure_schema_version_table(conn):
    """确保 schema_version 表存在"""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description VARCHAR(255)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))


def _get_current_schema_version(conn):
    """获取当前 schema 版本"""
    try:
        result = conn.execute(text("SELECT MAX(version) FROM schema_version"))
        version = result.scalar()
        return version if version is not None else 0
    except Exception:
        return 0


def _record_schema_version(conn, version, description=""):
    """记录 schema 版本"""
    conn.execute(
        text("INSERT INTO schema_version (version, description) VALUES (:v, :d) ON DUPLICATE KEY UPDATE applied_at=CURRENT_TIMESTAMP"),
        {"v": version, "d": description}
    )


def init_mysql_tables_v2():
    """
    优化版数据库初始化：使用 Schema 版本控制，避免每次启动全量迁移
    大幅提升启动速度，特别是数据量大时
    """
    engine = get_engine()

    with engine.begin() as conn:
        # 1. 确保基础表和版本表存在（这部分每次都执行，确保表结构存在）
        _ensure_schema_version_table(conn)

        # 获取当前版本
        current_version = _get_current_schema_version(conn)

        # 如果已经是最新版本，跳过大部分初始化
        if current_version >= CURRENT_SCHEMA_VERSION:
            # 只执行必要的轻量级检查（如默认用户）
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for uid, info in DEFAULT_USERS.items():
                conn.execute(text(
                    "INSERT IGNORE INTO users "
                    "(username, password, role, name, status, register_time, audit_time, auditor) "
                    "VALUES (:u, :p, :r, :n, 'active', :t, :t, 'System')"
                ), {"u": uid, "p": info["password"], "r": info["role"], "n": info["name"], "t": current_time})
            return {"initialized": False, "version": current_version, "message": "Schema already up to date"}

        # 2. 版本 0 -> 1：创建所有基础表（首次启动或旧版本升级）
        if current_version < 1:
            # 执行建表 DDL（简化版，只创建核心表，其他表按需创建）
            ddl_statements = [
                """
                CREATE TABLE IF NOT EXISTS finished_goods_data (
                    `流水号`        VARCHAR(100) NOT NULL,
                    `批次号`        VARCHAR(100) DEFAULT '',
                    `机型`          VARCHAR(100) DEFAULT '',
                    `状态`          VARCHAR(50)  DEFAULT '',
                    `预计入库时间`  DATETIME NULL,
                    `更新时间`      TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    `占用订单号`    VARCHAR(100) NULL,
                    `客户`          VARCHAR(200) DEFAULT '',
                    `代理商`        VARCHAR(200) DEFAULT '',
                    `合同备注`      TEXT,
                    `Location_Code` VARCHAR(100) DEFAULT '',
                    `合同号`        VARCHAR(100) DEFAULT '',
                    PRIMARY KEY (`流水号`),
                    INDEX `idx_fg_order` (`占用订单号`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS sales_orders (
                    `订单号`        VARCHAR(100) NOT NULL,
                    `客户名`        VARCHAR(200) DEFAULT '',
                    `代理商`        VARCHAR(200) DEFAULT '',
                    `需求机型`      TEXT,
                    `需求数量`      INT DEFAULT 0,
                    `下单时间`      DATETIME NULL,
                    `备注`          TEXT,
                    `包装选项`      VARCHAR(100) DEFAULT '',
                    `发货时间`      DATETIME NULL,
                    `指定批次/来源` JSON NULL,
                    `status`        VARCHAR(50)  DEFAULT 'active',
                    `delete_reason` TEXT,
                    PRIMARY KEY (`订单号`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS factory_plan (
                    `id`            INT NOT NULL AUTO_INCREMENT,
                    `合同号`        VARCHAR(100) DEFAULT '',
                    `机型`          VARCHAR(100) DEFAULT '',
                    `排产数量`      VARCHAR(20)  DEFAULT '',
                    `要求交期`      VARCHAR(50)  DEFAULT '',
                    `状态`          VARCHAR(50)  DEFAULT '',
                    `备注`          TEXT,
                    `客户名`        VARCHAR(200) DEFAULT '',
                    `代理商`        VARCHAR(200) DEFAULT '',
                    `指定批次/来源` JSON NULL,
                    `订单号`        VARCHAR(100) NULL,
                    PRIMARY KEY (`id`),
                    INDEX `idx_fp_order` (`订单号`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS plan_import (
                    `流水号`        VARCHAR(100) NOT NULL,
                    `批次号`        VARCHAR(100) DEFAULT '',
                    `机型`          VARCHAR(100) DEFAULT '',
                    `状态`          VARCHAR(50)  DEFAULT '待入库',
                    `预计入库时间`  DATETIME NULL,
                    `客户`          VARCHAR(200) DEFAULT '',
                    `代理商`        VARCHAR(200) DEFAULT '',
                    `合同备注`      TEXT,
                    `合同号`        VARCHAR(100) DEFAULT '',
                    `订单号`        VARCHAR(100) DEFAULT '',
                    PRIMARY KEY (`流水号`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS users (
                    `username`      VARCHAR(100) NOT NULL,
                    `password`      VARCHAR(200) DEFAULT '',
                    `role`          VARCHAR(50)  DEFAULT '',
                    `name`          VARCHAR(100) DEFAULT '',
                    `status`        VARCHAR(50)  DEFAULT 'pending',
                    `register_time` DATETIME NULL,
                    `audit_time`    DATETIME NULL,
                    `auditor`       VARCHAR(100) DEFAULT '',
                    PRIMARY KEY (`username`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS role_permissions (
                    `id`        INT NOT NULL AUTO_INCREMENT,
                    `role_id`   VARCHAR(50)  DEFAULT '',
                    `func_code` VARCHAR(100) DEFAULT '',
                    PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS rush_order_queue (
                    `id` BIGINT NOT NULL AUTO_INCREMENT,
                    `contract_no` VARCHAR(100) NOT NULL,
                    `customer` VARCHAR(200) DEFAULT '',
                    `dealer_name` VARCHAR(200) DEFAULT '',
                    `model_type` VARCHAR(100) NOT NULL,
                    `due_date` DATE NULL,
                    `remark` TEXT NULL,
                    `source` VARCHAR(50) NOT NULL DEFAULT 'contract',
                    `status` VARCHAR(30) NOT NULL DEFAULT 'pending',
                    `created_by` VARCHAR(100) DEFAULT '',
                    `updated_by` VARCHAR(100) DEFAULT '',
                    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (`id`),
                    INDEX `idx_rush_order_queue_status` (`status`, `created_at`),
                    INDEX `idx_rush_order_queue_contract` (`contract_no`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
            ]

            for ddl in ddl_statements:
                try:
                    conn.execute(text(ddl))
                except Exception as e:
                    # 表已存在时忽略错误
                    pass

            # 插入默认用户
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for uid, info in DEFAULT_USERS.items():
                conn.execute(text(
                    "INSERT IGNORE INTO users "
                    "(username, password, role, name, status, register_time, audit_time, auditor) "
                    "VALUES (:u, :p, :r, :n, 'active', :t, :t, 'System')"
                ), {"u": uid, "p": info["password"], "r": info["role"], "n": info["name"], "t": current_time})

            # 插入默认权限
            result = conn.execute(text("SELECT COUNT(*) FROM role_permissions"))
            if result.fetchone()[0] == 0:
                for role_id, func_codes in DEFAULT_ROLE_PERMISSIONS.items():
                    for func_code in func_codes:
                        conn.execute(
                            text("INSERT IGNORE INTO role_permissions (role_id, func_code) VALUES (:r, :f)"),
                            {"r": role_id, "f": func_code},
                        )

            # 记录版本
            _record_schema_version(conn, 1, "Initial schema creation")

        # 版本 1 → 2：plan_import 列结构调整（客户/代理商/合同备注 替代 机台备注/配置）
        if current_version < 2:
            def _column_exists_v2(t, c):
                raw = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND COLUMN_NAME=:c"
                ), {"db": MYSQL_DB, "t": t, "c": c}).scalar()
                try:
                    return int(raw or 0) > 0
                except Exception:
                    return False

            for col_name, col_def in [
                ("客户", "VARCHAR(200) DEFAULT '' AFTER `预计入库时间`"),
                ("代理商", "VARCHAR(200) DEFAULT '' AFTER `客户`"),
                ("合同备注", "TEXT AFTER `代理商`"),
                ("合同号", "VARCHAR(100) DEFAULT '' AFTER `合同备注`"),
                ("订单号", "VARCHAR(100) DEFAULT '' AFTER `合同号`"),
            ]:
                if not _column_exists_v2("plan_import", col_name):
                    try:
                        conn.execute(text(f"ALTER TABLE plan_import ADD COLUMN `{col_name}` {col_def}"))
                    except Exception:
                        pass
            if _column_exists_v2("plan_import", "机台备注/配置"):
                try:
                    conn.execute(text("ALTER TABLE plan_import DROP COLUMN `机台备注/配置`"))
                except Exception:
                    pass
            _record_schema_version(conn, 2, "plan_import: replace 机台备注/配置 with 客户, 代理商, 合同备注")

        # 版本 2 → 3：补齐合同号在 plan_import / finished_goods_data / shipping_history 的追溯链路
        if current_version < 3:
            def _column_exists_v3(t, c):
                raw = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND COLUMN_NAME=:c"
                ), {"db": MYSQL_DB, "t": t, "c": c}).scalar()
                try:
                    return int(raw or 0) > 0
                except Exception:
                    return False

            for table_name, after_col in [
                ("plan_import", "合同备注"),
                ("finished_goods_data", "Location_Code"),
                ("shipping_history", "合同备注"),
            ]:
                if not _column_exists_v3(table_name, "合同号"):
                    try:
                        conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `合同号` VARCHAR(100) DEFAULT '' AFTER `{after_col}`"))
                    except Exception:
                        pass
            _record_schema_version(conn, 3, "add contract_no traceability columns")

        # 版本 3 → 4：合同录入急单持久队列
        if current_version < 4:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS rush_order_queue (
                    `id` BIGINT NOT NULL AUTO_INCREMENT,
                    `contract_no` VARCHAR(100) NOT NULL,
                    `customer` VARCHAR(200) DEFAULT '',
                    `dealer_name` VARCHAR(200) DEFAULT '',
                    `model_type` VARCHAR(100) NOT NULL,
                    `due_date` DATE NULL,
                    `remark` TEXT NULL,
                    `source` VARCHAR(50) NOT NULL DEFAULT 'contract',
                    `status` VARCHAR(30) NOT NULL DEFAULT 'pending',
                    `created_by` VARCHAR(100) DEFAULT '',
                    `updated_by` VARCHAR(100) DEFAULT '',
                    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (`id`),
                    INDEX `idx_rush_order_queue_status` (`status`, `created_at`),
                    INDEX `idx_rush_order_queue_contract` (`contract_no`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            _record_schema_version(conn, 4, "add persistent rush order queue")

        # 版本 4 → 5：统一机台/订单备注为合同备注，并删除库存旧备注字段
        if current_version < 5:
            def _column_exists_v5(t, c):
                raw = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND COLUMN_NAME=:c"
                ), {"db": MYSQL_DB, "t": t, "c": c}).scalar()
                try:
                    return int(raw or 0) > 0
                except Exception:
                    return False

            for table_name, after_col in [
                ("finished_goods_data", "代理商"),
                ("shipping_history", "代理商"),
            ]:
                if not _column_exists_v5(table_name, "合同备注"):
                    try:
                        conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `合同备注` TEXT AFTER `{after_col}`"))
                    except Exception:
                        pass

            if _column_exists_v5("finished_goods_data", "合同备注"):
                try:
                    conn.execute(text("""
                        UPDATE finished_goods_data fg
                        LEFT JOIN factory_plan fp
                          ON fg.`合同号` = fp.`合同号` AND fg.`机型` = fp.`机型`
                        SET fg.`合同备注` = fp.`备注`
                        WHERE COALESCE(TRIM(fg.`合同备注`), '') = ''
                          AND COALESCE(TRIM(fp.`备注`), '') <> ''
                    """))
                except Exception:
                    pass
                try:
                    conn.execute(text("""
                        UPDATE finished_goods_data fg
                        LEFT JOIN plan_import pi ON fg.`流水号` = pi.`流水号`
                        SET fg.`合同备注` = pi.`合同备注`
                        WHERE COALESCE(TRIM(fg.`合同备注`), '') = ''
                          AND COALESCE(TRIM(pi.`合同备注`), '') <> ''
                    """))
                except Exception:
                    pass
                for legacy_col in ["订单备注", "机台备注/配置"]:
                    if _column_exists_v5("finished_goods_data", legacy_col):
                        try:
                            conn.execute(text(f"""
                                UPDATE finished_goods_data
                                SET `合同备注` = `{legacy_col}`
                                WHERE COALESCE(TRIM(`合同备注`), '') = ''
                                  AND COALESCE(TRIM(`{legacy_col}`), '') <> ''
                            """))
                        except Exception:
                            pass

            if _column_exists_v5("shipping_history", "合同备注"):
                try:
                    conn.execute(text("""
                        UPDATE shipping_history sh
                        LEFT JOIN factory_plan fp
                          ON sh.`合同号` = fp.`合同号` AND sh.`机型` = fp.`机型`
                        SET sh.`合同备注` = fp.`备注`
                        WHERE COALESCE(TRIM(sh.`合同备注`), '') = ''
                          AND COALESCE(TRIM(fp.`备注`), '') <> ''
                    """))
                except Exception:
                    pass
                for legacy_col in ["订单备注", "机台备注/配置"]:
                    if _column_exists_v5("shipping_history", legacy_col):
                        try:
                            conn.execute(text(f"""
                                UPDATE shipping_history
                                SET `合同备注` = `{legacy_col}`
                                WHERE COALESCE(TRIM(`合同备注`), '') = ''
                                  AND COALESCE(TRIM(`{legacy_col}`), '') <> ''
                            """))
                        except Exception:
                            pass

            for table_name in ["finished_goods_data", "shipping_history"]:
                for legacy_col in ["订单备注", "机台备注/配置"]:
                    if _column_exists_v5(table_name, legacy_col):
                        try:
                            conn.execute(text(f"ALTER TABLE `{table_name}` DROP COLUMN `{legacy_col}`"))
                        except Exception:
                            pass
            _record_schema_version(conn, 5, "unify machine/order notes into contract remarks")

        if current_version < 6:
            conn.execute(text("UPDATE factory_plan SET `状态`='待规划' WHERE TRIM(COALESCE(`状态`, ''))='未下单'"))
            conn.execute(text("UPDATE factory_plan SET `状态`='待规划' WHERE TRIM(COALESCE(`状态`, ''))=''"))
            _record_schema_version(conn, 6, "normalize factory_plan status to 待规划")

        if current_version < 7:
            raw = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=:db AND TABLE_NAME='rush_order_queue' AND COLUMN_NAME='remark'"
            ), {"db": MYSQL_DB}).scalar()
            try:
                has_remark = int(raw or 0) > 0
            except Exception:
                has_remark = False
            if not has_remark:
                conn.execute(text("ALTER TABLE rush_order_queue ADD COLUMN `remark` TEXT NULL AFTER `due_date`"))
            _record_schema_version(conn, 7, "add remark column for rush order queue")

        if current_version < 8:
            conn.execute(text(
                "UPDATE factory_plan SET `状态`='已转订单' "
                "WHERE TRIM(COALESCE(`状态`, ''))='已规划' "
                "AND COALESCE(TRIM(`订单号`), '') <> ''"
            ))
            _record_schema_version(conn, 8, "normalize planned contracts linked to orders")

        if current_version < 9:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dealer_orders (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  order_no VARCHAR(64) NOT NULL,
                  line_no INT NOT NULL DEFAULT 1,
                  dealer_id VARCHAR(128) NOT NULL,
                  dealer_name VARCHAR(255) NOT NULL,
                  dealer_phone VARCHAR(64) DEFAULT '',
                  customer_name VARCHAR(255) NOT NULL,
                  contact_name VARCHAR(128) NOT NULL,
                  contact_phone VARCHAR(64) NOT NULL,
                  model VARCHAR(255) NOT NULL,
                  batch_no VARCHAR(255) DEFAULT '',
                  eta VARCHAR(64) DEFAULT '',
                  inventory_type VARCHAR(32) DEFAULT '',
                  quantity INT NOT NULL DEFAULT 1,
                  approved_qty INT NOT NULL DEFAULT 0,
                  allocated_qty INT NOT NULL DEFAULT 0,
                  delivery_date VARCHAR(64) DEFAULT '',
                  remark TEXT,
                  extra_remark TEXT,
                  ERMQ INT NOT NULL DEFAULT 0,
                  factory_pending TINYINT(1) NOT NULL DEFAULT 0,
                  source VARCHAR(32) NOT NULL DEFAULT 'wechat',
                  last_synced_at DATETIME NULL,
                  sync_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  sync_error TEXT,
                  factory_reviewed_at DATETIME NULL,
                  factory_reviewed_by VARCHAR(128) DEFAULT '',
                  extra_remark_reviewed_at DATETIME NULL,
                  extra_remark_reviewed_by VARCHAR(128) DEFAULT '',
                  status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  reviewed_at DATETIME NULL,
                  reviewed_by VARCHAR(128) DEFAULT '',
                  contract_no VARCHAR(128) DEFAULT '',
                  v7_order_no VARCHAR(128) DEFAULT '',
                  review_note TEXT,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uq_dealer_order_line (order_no, line_no),
                  INDEX idx_dealer_order_no (order_no),
                  INDEX idx_dealer_id (dealer_id),
                  INDEX idx_status (status),
                  INDEX idx_batch_model_status (batch_no, model, status),
                  INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dealer_order_sync_events (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  event_id VARCHAR(64) NOT NULL UNIQUE,
                  order_no VARCHAR(64) NOT NULL,
                  event_type VARCHAR(64) NOT NULL,
                  source VARCHAR(32) NOT NULL DEFAULT 'wechat',
                  payload_json JSON NULL,
                  status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  attempts INT NOT NULL DEFAULT 0,
                  last_error TEXT,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  acked_at DATETIME NULL,
                  INDEX idx_sync_events_order (order_no),
                  INDEX idx_sync_events_status (status, id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS wechat_batch_summary (
                  summary_id CHAR(32) NOT NULL,
                  batch_no VARCHAR(100) NOT NULL,
                  expected_inbound_time DATETIME NULL,
                  model VARCHAR(100) NOT NULL,
                  quantity INT NOT NULL DEFAULT 0,
                  批次号 VARCHAR(100) NOT NULL,
                  预计入库时间 DATETIME NULL,
                  机型 VARCHAR(100) NOT NULL,
                  数量 INT NOT NULL DEFAULT 0,
                  更新时间 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (summary_id),
                  INDEX idx_wbs_batch (批次号),
                  INDEX idx_wbs_inbound (预计入库时间),
                  INDEX idx_wbs_model (机型)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            _record_schema_version(conn, 9, "add dealer_orders and wechat_batch_summary tables")

        return {
            "initialized": True,
            "from_version": current_version,
            "to_version": CURRENT_SCHEMA_VERSION,
            "message": f"Schema upgraded from {current_version} to {CURRENT_SCHEMA_VERSION}"
        }
