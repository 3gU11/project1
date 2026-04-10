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
        "DROP INDEX idx_import_batch_model ON plan_import",
        "DROP INDEX idx_ship_month_time ON shipping_history",
        "DROP INDEX uq_contract_path ON contract_records",
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
        connect_args={"auth_plugin_map": {"caching_sha2_password": "mysql_native_password", "sha256_password": "mysql_native_password"}},
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
            `订单备注`      TEXT,
            `机台备注/配置` TEXT,
            `Location_Code` VARCHAR(100) DEFAULT '',
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
            `订单备注`      TEXT,
            `机台备注/配置` TEXT,
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
            `机台备注/配置` TEXT,
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
        for role_id, func_codes in DEFAULT_ROLE_PERMISSIONS.items():
            for func_code in func_codes:
                conn.execute(
                    text("INSERT IGNORE INTO role_permissions (role_id, func_code) VALUES (:r, :f)"),
                    {"r": role_id, "f": func_code},
                )
        sales_perms = DEFAULT_ROLE_PERMISSIONS.get("Sales", [])
        conn.execute(text("DELETE FROM role_permissions WHERE role_id='Sales'"))
        for func_code in sales_perms:
            conn.execute(
                text("INSERT IGNORE INTO role_permissions (role_id, func_code) VALUES (:r, :f)"),
                {"r": "Sales", "f": func_code},
            )
