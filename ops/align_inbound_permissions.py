"""按约定矩阵对齐本地 `INBOUND`（成品入库）角色权限。

允许拥有成品入库权限的角色：Admin、Boss、Prod、Inbound。
其余角色（含 Sales、AfterSales、LineOperator 及自定义角色）一律移除 INBOUND。

用法：
    python scripts/align_inbound_permissions.py           # 只读预览
    python scripts/align_inbound_permissions.py --apply   # 实际写入

说明：
- 只增删 `role_permissions` 中的 INBOUND，不改动其他功能权限；
- 不创建/删除角色和用户；
- 权限改动对后端立即生效，前端登录态里缓存的 permissions 需要重新登录后刷新。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_engine

ALLOWED_ROLES = ("admin", "boss", "prod", "inbound")


def _fetch_inbound_roles(conn) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT role_id FROM role_permissions "
            "WHERE UPPER(TRIM(func_code)) = 'INBOUND' ORDER BY role_id"
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def _fetch_all_roles(conn) -> list[str]:
    rows = conn.execute(text("SELECT role_id FROM roles ORDER BY role_id")).fetchall()
    return [str(row[0]) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="按矩阵对齐 INBOUND 角色权限")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认仅预览")
    args = parser.parse_args()

    with get_engine().begin() as conn:
        roles = _fetch_all_roles(conn)
        before = _fetch_inbound_roles(conn)

        print("角色列表:", ", ".join(roles) or "(空)")
        print("调整前拥有 INBOUND:", ", ".join(before) or "(无)")

        if not args.apply:
            target = [role for role in roles if role.strip().lower() in ALLOWED_ROLES]
            removed = [role for role in before if role.strip().lower() not in ALLOWED_ROLES]
            print("应保留:", ", ".join(target) or "(无)")
            print("应移除:", ", ".join(removed) or "(无)")
            print("预览模式：未写入。确认后追加 --apply 执行。")
            return 0

        deleted = conn.execute(
            text(
                "DELETE FROM role_permissions "
                "WHERE UPPER(TRIM(func_code)) = 'INBOUND' "
                "AND LOWER(TRIM(role_id)) NOT IN ('admin', 'boss', 'prod', 'inbound')"
            )
        ).rowcount

        inserted = 0
        for role in roles:
            if role.strip().lower() not in ALLOWED_ROLES:
                continue
            result = conn.execute(
                text(
                    "INSERT IGNORE INTO role_permissions (role_id, func_code) "
                    "VALUES (:role_id, 'INBOUND')"
                ),
                {"role_id": role},
            )
            inserted += max(int(result.rowcount or 0), 0)

        after = _fetch_inbound_roles(conn)
        print(f"实际删除 {deleted} 条，补齐 {inserted} 条")
        print("调整后拥有 INBOUND:", ", ".join(after) or "(无)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
