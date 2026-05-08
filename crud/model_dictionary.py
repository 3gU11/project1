from __future__ import annotations

from typing import Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.exc import OperationalError

from database import get_engine

MODEL_CATEGORIES = {"大机AUTO", "小机AUTO", "大机XS", "小机XS", "小机G", "特殊"}


def _clean_name(name: object) -> str:
    return str(name or "").strip()


def _normalize_family(value: object) -> str:
    family = str(value or "").strip()
    if family == "小机/XS":
        family = "小机XS"
    if not family:
        return ""
    if family not in MODEL_CATEGORIES:
        raise RuntimeError(f"model_family invalid: {family}")
    return family


def ensure_model_dictionary_table() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS model_dictionary (
        `id` INT NOT NULL AUTO_INCREMENT,
        `model_name` VARCHAR(100) NOT NULL,
        `model_family` VARCHAR(32) NULL,
        `sort_order` INT NOT NULL DEFAULT 0,
        `enabled` TINYINT(1) NOT NULL DEFAULT 1,
        `remark` VARCHAR(255) DEFAULT '',
        `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (`id`),
        UNIQUE KEY `uq_model_dictionary_name` (`model_name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    with get_engine().begin() as conn:
        conn.execute(text(ddl))
        has_family = conn.execute(text("SHOW COLUMNS FROM model_dictionary LIKE 'model_family'")).fetchone()
        if not has_family:
            conn.execute(text("ALTER TABLE model_dictionary ADD COLUMN `model_family` VARCHAR(32) NULL AFTER `model_name`"))
        next_order = int(conn.execute(text("SELECT COALESCE(MAX(`sort_order`), -1) + 1 FROM model_dictionary")).scalar() or 0)
        exists = conn.execute(
            text("SELECT `id` FROM model_dictionary WHERE UPPER(TRIM(`model_name`)) = 'FH-300C' LIMIT 1")
        ).fetchone()
        if exists:
            conn.execute(
                text(
                    "UPDATE model_dictionary "
                    "SET `model_name`='FH-300C', `model_family`='小机G', `enabled`=1 "
                    "WHERE UPPER(TRIM(`model_name`)) = 'FH-300C'"
                )
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO model_dictionary (`model_name`, `model_family`, `sort_order`, `enabled`, `remark`) "
                    "VALUES ('FH-300C', '小机G', :sort_order, 1, '老板计划小机G机型')"
                ),
                {"sort_order": next_order},
            )


def get_model_dictionary() -> list[dict]:
    try:
        ensure_model_dictionary_table()
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT `id`, `model_name`, `model_family`, `sort_order`, `enabled`, `remark`, `updated_at` "
                    "FROM model_dictionary "
                    "ORDER BY `sort_order` ASC, `id` ASC"
                )
            ).mappings().all()
        return [dict(r) for r in rows]
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"读取机型字典失败: {e}") from e


def get_enabled_model_names() -> list[str]:
    try:
        ensure_model_dictionary_table()
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT `model_name` FROM model_dictionary "
                    "WHERE `enabled`=1 "
                    "ORDER BY `sort_order` ASC, `id` ASC"
                )
            ).fetchall()
        return [_clean_name(r[0]) for r in rows if _clean_name(r[0])]
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"读取机型字典失败: {e}") from e


def is_model_enabled(model_name: object) -> bool:
    clean = _clean_name(model_name).replace("(加高)", "").strip()
    if not clean:
        return False
    try:
        return clean in set(get_enabled_model_names())
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"校验机型失败: {e}") from e


def find_disabled_models(model_names: Iterable[object]) -> list[str]:
    enabled = set(get_enabled_model_names())
    invalid: list[str] = []
    seen = set()
    for name in model_names or []:
        clean = _clean_name(name).replace("(加高)", "").strip()
        if not clean or clean in enabled or clean in seen:
            continue
        seen.add(clean)
        invalid.append(clean)
    return invalid


def save_model_dictionary(rows: Iterable[dict]) -> int:
    try:
        cleaned: list[dict] = []
        seen = set()
        for idx, row in enumerate(rows or []):
            model_name = _clean_name(row.get("model_name"))
            if not model_name:
                raise RuntimeError("机型名称不能为空")
            if model_name in seen:
                raise RuntimeError("机型名称不能重复")
            seen.add(model_name)
            item_id = int(row.get("id")) if row.get("id") is not None and str(row.get("id")).strip() else None
            enabled = 1 if bool(row.get("enabled", True)) else 0
            remark = str(row.get("remark") or "").strip()
            model_family = _normalize_family(row.get("model_family"))
            cleaned.append(
                {
                    "id": item_id,
                    "model_name": model_name,
                    "model_family": model_family or None,
                    "sort_order": idx,
                    "enabled": enabled,
                    "remark": remark,
                }
            )

        if not cleaned:
            raise RuntimeError("至少保留 1 个机型")

        with get_engine().begin() as conn:
            ensure_model_dictionary_table()
            existing_ids = {
                int(v)
                for v in conn.execute(text("SELECT `id` FROM model_dictionary")).scalars().all()
                if v is not None
            }
            incoming_ids = [row["id"] for row in cleaned if row["id"] in existing_ids]

            if incoming_ids:
                delete_stmt = text("DELETE FROM model_dictionary WHERE `id` NOT IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                )
                conn.execute(delete_stmt, {"ids": incoming_ids})
            else:
                conn.execute(text("DELETE FROM model_dictionary"))

            for row in cleaned:
                item_id = row["id"]
                if item_id in existing_ids:
                    result = conn.execute(
                        text(
                            "UPDATE model_dictionary "
                            "SET `model_name`=:model_name, `model_family`=:model_family, "
                            "`sort_order`=:sort_order, `enabled`=:enabled, `remark`=:remark "
                            "WHERE `id`=:id"
                        ),
                        row,
                    )
                    if int(result.rowcount or 0) > 0:
                        continue

                conn.execute(
                    text(
                        "INSERT INTO model_dictionary (`model_name`, `model_family`, `sort_order`, `enabled`, `remark`) "
                        "VALUES (:model_name, :model_family, :sort_order, :enabled, :remark)"
                    ),
                    {
                        "model_name": row["model_name"],
                        "model_family": row["model_family"],
                        "sort_order": row["sort_order"],
                        "enabled": row["enabled"],
                        "remark": row["remark"],
                    },
                )
        return len(cleaned)
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"保存机型字典失败: {e}") from e


def seed_model_dictionary_if_empty() -> int:
    try:
        ensure_model_dictionary_table()
        with get_engine().begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM model_dictionary")).scalar() or 0
            if int(count) > 0:
                return 0
            return 0
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"初始化机型字典失败: {e}") from e


def delete_model_dictionary_item(model_name: object = "", item_id: object = None) -> int:
    name = _clean_name(model_name)
    id_val = int(item_id) if item_id is not None and str(item_id).strip() else None
    if id_val is None and not name:
        raise RuntimeError("机型名称不能为空")
    try:
        with get_engine().begin() as conn:
            total = int(conn.execute(text("SELECT COUNT(*) FROM model_dictionary")).scalar() or 0)
            if total <= 1:
                raise RuntimeError("至少保留 1 个机型")
            if id_val is not None:
                result = conn.execute(
                    text("DELETE FROM model_dictionary WHERE `id`=:id"),
                    {"id": id_val},
                )
            else:
                result = conn.execute(
                    text("DELETE FROM model_dictionary WHERE `model_name`=:name"),
                    {"name": name},
                )
            return int(result.rowcount or 0)
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"删除机型失败: {e}") from e


def replace_model_name_globally(old_name: object, new_name: object) -> dict:
    old_clean = _clean_name(old_name)
    new_clean = _clean_name(new_name)
    if not old_clean or not new_clean:
        raise RuntimeError("旧机型和新机型不能为空")
    if old_clean == new_clean:
        return {
            "old_name": old_clean,
            "new_name": new_clean,
            "finished_goods_data": 0,
            "factory_plan": 0,
            "plan_import": 0,
            "sales_orders": 0,
            "total": 0,
        }

    try:
        with get_engine().begin() as conn:
            c1 = conn.execute(
                text("UPDATE finished_goods_data SET `机型`=:new WHERE TRIM(`机型`)=:old"),
                {"old": old_clean, "new": new_clean},
            ).rowcount or 0
            c2 = conn.execute(
                text("UPDATE factory_plan SET `机型`=:new WHERE TRIM(`机型`)=:old"),
                {"old": old_clean, "new": new_clean},
            ).rowcount or 0
            c3 = conn.execute(
                text("UPDATE plan_import SET `机型`=:new WHERE TRIM(`机型`)=:old"),
                {"old": old_clean, "new": new_clean},
            ).rowcount or 0
            c4 = conn.execute(
                text("UPDATE sales_orders SET `需求机型`=REPLACE(`需求机型`, :old, :new) WHERE `需求机型` LIKE :pat"),
                {"old": old_clean, "new": new_clean, "pat": f"%{old_clean}%"},
            ).rowcount or 0

        total = int(c1) + int(c2) + int(c3) + int(c4)
        return {
            "old_name": old_clean,
            "new_name": new_clean,
            "finished_goods_data": int(c1),
            "factory_plan": int(c2),
            "plan_import": int(c3),
            "sales_orders": int(c4),
            "total": total,
        }
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"全局替换机型失败: {e}") from e
