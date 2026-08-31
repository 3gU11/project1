"""Read-only V8 repair component catalogue for a machine model."""

from sqlalchemy import text

from database import get_engine


def find_repair_models() -> list[dict]:
    statement = text("""
        SELECT model.model_name, model.model_family, model.sort_order
        FROM model_dictionary model
        JOIN model_photo_config cfg ON cfg.model_id = model.id AND cfg.enabled = 1
        JOIN photo_item_library library ON library.position_code = cfg.position_code AND library.enabled = 1
        WHERE model.enabled = 1
        GROUP BY model.id, model.model_name, model.model_family, model.sort_order
        ORDER BY model.sort_order, model.model_name
    """)
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings().all()]


def find_repair_model_components(model_name: str) -> list[dict]:
    """Return enabled photo/identity positions configured for one V8 model."""
    normalized = str(model_name or "").strip()
    if not normalized:
        return []
    statement = text("""
        SELECT cfg.position_code, library.item_name, library.item_category,
               library.shooting_requirement, cfg.required, cfg.ocr_enabled,
               cfg.ocr_profile, cfg.sort_order, cfg.updated_at
        FROM model_photo_config cfg
        JOIN model_dictionary model ON model.id = cfg.model_id
        JOIN photo_item_library library ON library.position_code = cfg.position_code
        WHERE model.model_name = :model_name
          AND model.enabled = 1
          AND cfg.enabled = 1
          AND library.enabled = 1
          AND library.position_code LIKE 'SN-%'
        ORDER BY cfg.sort_order, cfg.id
    """)
    with get_engine().connect() as connection:
        rows = connection.execute(statement, {"model_name": normalized}).mappings().all()
    return [dict(row) for row in rows]
