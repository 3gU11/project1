from __future__ import annotations

from datetime import datetime, timedelta
import re

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import get_engine


OPERATION_LOG_COLUMNS = ["时间", "姓名", "模块", "操作类型", "业务对象", "操作内容"]


def _split_action(action: object) -> tuple[str, str]:
    raw = str(action or "").strip()
    if not raw:
        return "", ""
    if "-" in raw:
        module, operation = raw.split("-", 1)
        return module.strip(), operation.strip()
    return "系统管理", raw


def _normalize_text(value: object, default: str = "") -> str:
    normalized = str(value or "").strip()
    return normalized or default


def _extract_log_identifier(content: str, labels: list[str], patterns: list[str] | None = None) -> str:
    text_value = _normalize_text(content)
    if not text_value:
        return ""
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^；;，,\s]+)", text_value)
        if match:
            return match.group(1).strip()
    for pattern in patterns or []:
        match = re.search(pattern, text_value, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _ensure_operation_log_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS sys_operation_log (
        `id` BIGINT NOT NULL AUTO_INCREMENT,
        `user_id` VARCHAR(100) DEFAULT '',
        `username` VARCHAR(100) DEFAULT '',
        `operate_time` DATETIME NULL,
        `module` VARCHAR(100) DEFAULT '',
        `action_type` VARCHAR(100) DEFAULT '',
        `biz_type` VARCHAR(100) DEFAULT '',
        `serial_no` VARCHAR(100) DEFAULT '',
        `order_no` VARCHAR(100) DEFAULT '',
        `contract_no` VARCHAR(100) DEFAULT '',
        `content` TEXT,
        PRIMARY KEY (`id`),
        INDEX `idx_sys_operation_log_time` (`operate_time`),
        INDEX `idx_sys_operation_log_user` (`user_id`, `operate_time`),
        INDEX `idx_sys_operation_log_module` (`module`, `action_type`, `biz_type`),
        INDEX `idx_sys_operation_log_sn` (`serial_no`),
        INDEX `idx_sys_operation_log_order` (`order_no`),
        INDEX `idx_sys_operation_log_contract` (`contract_no`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))
        try:
            conn.execute(text("ALTER TABLE sys_operation_log ADD COLUMN `serial_no` VARCHAR(100) DEFAULT ''"))
            conn.execute(text("ALTER TABLE sys_operation_log ADD COLUMN `order_no` VARCHAR(100) DEFAULT ''"))
            conn.execute(text("ALTER TABLE sys_operation_log ADD COLUMN `contract_no` VARCHAR(100) DEFAULT ''"))
            conn.execute(text("CREATE INDEX `idx_sys_operation_log_sn` ON sys_operation_log (`serial_no`)"))
            conn.execute(text("CREATE INDEX `idx_sys_operation_log_order` ON sys_operation_log (`order_no`)"))
            conn.execute(text("CREATE INDEX `idx_sys_operation_log_contract` ON sys_operation_log (`contract_no`)"))
        except Exception:
            pass


def _infer_biz_type(module: str, action_type: str, content: str) -> str:
    haystack = f"{module} {action_type} {content}".lower()
    mapping = [
        ("用户", "用户"),
        ("订单", "订单"),
        ("合同", "合同"),
        ("付款单", "付款单"),
        ("机型", "机型"),
        ("机台档案", "机台档案"),
        ("机台", "机台"),
        ("发货", "发货"),
        ("库存", "库存"),
    ]
    for keyword, biz_type in mapping:
        if keyword.lower() in haystack:
            return biz_type
    if "contract" in haystack:
        return "合同附件"
    if "archive" in haystack:
        return "机台档案"
    return ""


def append_operation_log(
    module: object,
    action_type: object,
    biz_type: object = "",
    content: object = "",
    *,
    user_id: object = "",
    username: object = "",
    operate_time: datetime | None = None,
    serial_no: str = "",
    order_no: str = "",
    contract_no: str = "",
) -> None:
    module_text = _normalize_text(module)
    action_text = _normalize_text(action_type)
    if not module_text and not action_text:
        return

    display_name = _normalize_text(username, "System")
    operator_id = _normalize_text(user_id, display_name)
    content_text = _normalize_text(content)
    
    if not serial_no:
        serial_no = _extract_log_identifier(content_text, ["流水号", "机台流水号"], [r"\b([A-Za-z0-9]+-[A-Za-z0-9-]+)\b"])
    if not order_no:
        order_no = _extract_log_identifier(content_text, ["订单号", "创建订单", "订单"], [r"\b(SO[-A-Za-z0-9]+)\b"])
    if not contract_no:
        contract_no = _extract_log_identifier(content_text, ["合同号", "合同"], [r"\b([A-Za-z]*C[A-Za-z0-9-]+)\b"])

    row = {
        "user_id": operator_id,
        "username": display_name,
        "operate_time": operate_time or datetime.now(),
        "module": module_text,
        "action_type": action_text,
        "biz_type": _normalize_text(biz_type) or _infer_biz_type(module_text, action_text, content_text),
        "serial_no": serial_no,
        "order_no": order_no,
        "contract_no": contract_no,
        "content": content_text,
    }
    try:
        _ensure_operation_log_table()
        pd.DataFrame([row]).to_sql("sys_operation_log", get_engine(), if_exists="append", index=False, method="multi")
    except (OperationalError, Exception):
        # Never block the main business flow because of operation logging failures.
        pass


def append_audit_log(
    action: object = "",
    details: object = "",
    user: object = "System",
    ip: object = "Local",
    *,
    module: object | None = None,
    action_type: object | None = None,
    biz_type: object = "",
    content: object | None = None,
    user_id: object | None = None,
    username: object | None = None,
) -> None:
    del ip  # 保留参数仅用于兼容旧调用。

    if module is not None or action_type is not None or content is not None or user_id is not None or username is not None:
        append_operation_log(
            module=module or "",
            action_type=action_type or action or "",
            biz_type=biz_type,
            content=details if content is None else content,
            user_id=user if user_id is None else user_id,
            username=user if username is None else username,
        )
        return

    module_text, action_text = _split_action(action)
    append_operation_log(
        module=module_text,
        action_type=action_text,
        biz_type=biz_type,
        content=details,
        user_id=user,
        username=user,
    )


def get_operation_logs(
    page: int = 1,
    page_size: int = 50,
    user: str = "",
    module: str = "",
    operation: str = "",
    biz_type: str = "",
    serial_no: str = "",
    contract_no: str = "",
    order_no: str = "",
    days: int = 14,
) -> tuple[pd.DataFrame, int]:
    try:
        _ensure_operation_log_table()
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        days = max(1, int(days))
        offset = (page - 1) * page_size
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        where_clauses = ["`operate_time` >= :cutoff"]
        params: dict[str, object] = {"limit": page_size, "offset": offset, "cutoff": cutoff}

        if _normalize_text(user):
            where_clauses.append("(`username` LIKE :user OR `user_id` LIKE :user)")
            params["user"] = f"%{_normalize_text(user)}%"
        if _normalize_text(module):
            where_clauses.append("`module` LIKE :module")
            params["module"] = f"%{_normalize_text(module)}%"
        if _normalize_text(operation):
            where_clauses.append("`action_type` LIKE :operation")
            params["operation"] = f"%{_normalize_text(operation)}%"
        if _normalize_text(biz_type):
            where_clauses.append("`biz_type` LIKE :biz_type")
            params["biz_type"] = f"%{_normalize_text(biz_type)}%"
        if _normalize_text(serial_no):
            where_clauses.append("(`serial_no` LIKE :serial_no OR `content` LIKE :serial_no)")
            params["serial_no"] = f"%{_normalize_text(serial_no)}%"
        if _normalize_text(contract_no):
            where_clauses.append("(`contract_no` LIKE :contract_no OR `content` LIKE :contract_no)")
            params["contract_no"] = f"%{_normalize_text(contract_no)}%"
        if _normalize_text(order_no):
            where_clauses.append("(`order_no` LIKE :order_no OR `content` LIKE :order_no)")
            params["order_no"] = f"%{_normalize_text(order_no)}%"

        where_sql = f" WHERE {' AND '.join(where_clauses)}"
        count_sql = text(f"SELECT COUNT(*) FROM sys_operation_log{where_sql}")
        sql = text(
            "SELECT `operate_time`, `username`, `module`, `action_type`, `biz_type`, `content` "
            f"FROM sys_operation_log{where_sql} "
            "ORDER BY `operate_time` DESC, `id` DESC "
            "LIMIT :limit OFFSET :offset"
        )
        with get_engine().connect() as conn:
            total = conn.execute(count_sql, params).scalar() or 0
            df = pd.read_sql(sql, conn, params=params)

        if df.empty:
            return pd.DataFrame(columns=OPERATION_LOG_COLUMNS), int(total)

        df["时间"] = df["operate_time"]
        df["姓名"] = df["username"].fillna("").astype(str)
        df["模块"] = df["module"].fillna("").astype(str)
        df["操作类型"] = df["action_type"].fillna("").astype(str)
        df["业务对象"] = df["biz_type"].fillna("").astype(str)
        df["操作内容"] = df["content"].fillna("").astype(str)
        return df[OPERATION_LOG_COLUMNS], int(total)
    except (OperationalError, Exception):
        return pd.DataFrame(columns=OPERATION_LOG_COLUMNS), 0


def get_audit_logs(
    page: int = 1,
    page_size: int = 50,
    user: str = "",
    module: str = "",
    operation: str = "",
    days: int = 14,
) -> tuple[pd.DataFrame, int]:
    return get_operation_logs(
        page=page,
        page_size=page_size,
        user=user,
        module=module,
        operation=operation,
        days=days,
    )
