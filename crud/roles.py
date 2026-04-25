from __future__ import annotations

from typing import Iterable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config import DEFAULT_ROLE_PERMISSIONS
from database import get_engine


def ensure_role_tables() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS roles ("
            "`role_id` VARCHAR(50) COLLATE utf8mb4_general_ci NOT NULL,"
            "`role_name` VARCHAR(100) COLLATE utf8mb4_general_ci DEFAULT '',"
            "PRIMARY KEY (`role_id`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"
        ))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS role_permissions ("
            "`id` INT NOT NULL AUTO_INCREMENT,"
            "`role_id` VARCHAR(50) COLLATE utf8mb4_general_ci DEFAULT '',"
            "`func_code` VARCHAR(100) COLLATE utf8mb4_general_ci DEFAULT '',"
            "PRIMARY KEY (`id`),"
            "UNIQUE KEY `uq_role_permissions_role_func` (`role_id`, `func_code`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"
        ))
        for sql in (
            "ALTER TABLE roles CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci",
            "ALTER TABLE role_permissions CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci",
        ):
            try:
                conn.execute(text(sql))
            except Exception:
                pass

PERMISSION_CATALOG = [
    {"code": "PLANNING", "label": "生产统筹/订单规划", "group": "管理与统筹"},
    {"code": "CONTRACT", "label": "合同管理", "group": "管理与统筹"},
    {"code": "MODEL_DICTIONARY", "label": "机型字典", "group": "系统管理"},
    {"code": "USER_MANAGE", "label": "用户管理", "group": "系统管理"},
    {"code": "SALES_CREATE", "label": "销售下单", "group": "销售"},
    {"code": "SALES_ALLOC", "label": "订单配货", "group": "销售"},
    {"code": "SHIP_CONFIRM", "label": "发货复核", "group": "生产/仓储"},
    {"code": "ARCHIVE", "label": "机台档案", "group": "生产/仓储"},
    {"code": "MACHINE_EDIT", "label": "机台编辑", "group": "生产/仓储"},
    {"code": "WAREHOUSE_MAP", "label": "库位大屏", "group": "生产/仓储"},
    {"code": "LOG_VIEW", "label": "交易日志", "group": "日志"},
    {"code": "QUERY", "label": "库存查询", "group": "查询"},
    {"code": "INBOUND", "label": "成品入库", "group": "生产/仓储"},
    {"code": "TRACEABILITY", "label": "汇总与追溯", "group": "查询"},
]

PERMISSION_CODES = {item["code"] for item in PERMISSION_CATALOG}


def normalize_role_id(role_id: str) -> str:
    return str(role_id or "").strip()


def get_permission_catalog() -> list[dict]:
    return list(PERMISSION_CATALOG)


def get_all_permission_codes() -> list[str]:
    return [item["code"] for item in PERMISSION_CATALOG]


def seed_roles_and_permissions_if_empty() -> None:
    ensure_role_tables()
    engine = get_engine()
    with engine.begin() as conn:
        for role_id, func_codes in DEFAULT_ROLE_PERMISSIONS.items():
            rid = normalize_role_id(role_id)
            if not rid:
                continue
            conn.execute(
                text("INSERT IGNORE INTO roles (role_id, role_name) VALUES (:rid, :rname)"),
                {"rid": rid, "rname": rid},
            )
            existing = conn.execute(
                text("SELECT COUNT(*) FROM role_permissions WHERE role_id=:rid"),
                {"rid": rid},
            ).scalar() or 0
            if existing == 0:
                for func_code in func_codes:
                    if func_code in PERMISSION_CODES:
                        conn.execute(
                            text("INSERT IGNORE INTO role_permissions (role_id, func_code) VALUES (:rid, :func)"),
                            {"rid": rid, "func": func_code},
                        )


def list_roles() -> list[dict]:
    seed_roles_and_permissions_if_empty()
    with get_engine().connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT r.role_id, r.role_name, "
                "COUNT(u.username) AS user_count "
                "FROM roles r "
                "LEFT JOIN users u ON u.role COLLATE utf8mb4_general_ci = r.role_id COLLATE utf8mb4_general_ci "
                "GROUP BY r.role_id, r.role_name "
                "ORDER BY r.role_id"
            ),
            conn,
        )
    df = df.where(df.notnull(), None)
    return df.to_dict(orient="records")


def role_exists(role_id: str) -> bool:
    ensure_role_tables()
    rid = normalize_role_id(role_id)
    if not rid:
        return False
    with get_engine().connect() as conn:
        return bool(conn.execute(text("SELECT 1 FROM roles WHERE role_id=:rid LIMIT 1"), {"rid": rid}).fetchone())


def create_role(role_id: str, role_name: str) -> dict:
    ensure_role_tables()
    rid = normalize_role_id(role_id)
    rname = str(role_name or "").strip() or rid
    if not rid:
        raise ValueError("角色编码不能为空")
    if rid.upper() in {"NULL", "NONE"}:
        raise ValueError("角色编码不合法")
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text("INSERT INTO roles (role_id, role_name) VALUES (:rid, :rname)"),
                {"rid": rid, "rname": rname},
            )
        return {"role_id": rid, "role_name": rname}
    except IntegrityError as exc:
        raise ValueError("角色已存在") from exc


def update_role(role_id: str, role_name: str) -> dict:
    ensure_role_tables()
    rid = normalize_role_id(role_id)
    rname = str(role_name or "").strip()
    if not rid or not rname:
        raise ValueError("角色编码和角色名称不能为空")
    with get_engine().begin() as conn:
        result = conn.execute(
            text("UPDATE roles SET role_name=:rname WHERE role_id=:rid"),
            {"rid": rid, "rname": rname},
        )
        if result.rowcount <= 0:
            raise ValueError("角色不存在")
    return {"role_id": rid, "role_name": rname}


def count_role_users(role_id: str) -> int:
    ensure_role_tables()
    rid = normalize_role_id(role_id)
    with get_engine().connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM users WHERE role=:rid"), {"rid": rid}).scalar() or 0)


def count_roles_with_permission(func_code: str) -> int:
    ensure_role_tables()
    with get_engine().connect() as conn:
        return int(
            conn.execute(
                text("SELECT COUNT(DISTINCT role_id) FROM role_permissions WHERE func_code=:func"),
                {"func": func_code},
            ).scalar()
            or 0
        )


def delete_role(role_id: str, current_role: str = "") -> None:
    rid = normalize_role_id(role_id)
    if not rid:
        raise ValueError("角色编码不能为空")
    if rid == normalize_role_id(current_role):
        raise ValueError("不能删除当前登录用户所属角色")
    if count_role_users(rid) > 0:
        raise ValueError("该角色下仍有用户，请先调整用户角色后再删除")
    perms = get_role_permissions(rid)
    if "USER_MANAGE" in perms and count_roles_with_permission("USER_MANAGE") <= 1:
        raise ValueError("不能删除最后一个拥有用户管理权限的角色")
    with get_engine().begin() as conn:
        result = conn.execute(text("DELETE FROM roles WHERE role_id=:rid"), {"rid": rid})
        if result.rowcount <= 0:
            raise ValueError("角色不存在")


def get_role_permissions(role_id: str) -> list[str]:
    rid = normalize_role_id(role_id)
    if not rid:
        return []
    seed_roles_and_permissions_if_empty()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT func_code FROM role_permissions WHERE role_id=:rid ORDER BY func_code"),
            {"rid": rid},
        ).fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]


def set_role_permissions(role_id: str, permissions: Iterable[str]) -> list[str]:
    rid = normalize_role_id(role_id)
    if not rid:
        raise ValueError("角色编码不能为空")
    if not role_exists(rid):
        raise ValueError("角色不存在")
    cleaned = []
    for item in permissions or []:
        code = str(item or "").strip()
        if code and code in PERMISSION_CODES and code not in cleaned:
            cleaned.append(code)
    if "USER_MANAGE" in get_role_permissions(rid) and "USER_MANAGE" not in cleaned and count_roles_with_permission("USER_MANAGE") <= 1:
        raise ValueError("不能移除最后一个用户管理权限")
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM role_permissions WHERE role_id=:rid"), {"rid": rid})
        for code in cleaned:
            conn.execute(
                text("INSERT IGNORE INTO role_permissions (role_id, func_code) VALUES (:rid, :func)"),
                {"rid": rid, "func": code},
            )
    return cleaned
