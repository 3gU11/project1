from __future__ import annotations


MODEL_FAMILY_ALIASES = {
    "大机XS": "中大型XS",
    "大机AUTO": "中大型AUTO",
    "小机XS": "中小型XS",
    "小机/XS": "中小型XS",
    "小机AUTO": "中小型AUTO",
    "小机G": "中小型G",
    "SPECIAL": "特殊",
}

PRODUCTION_GROUP_BY_FAMILY = {
    "中大型XS": "LARGE",
    "中大型AUTO": "LARGE",
    "中小型G": "SMALL_G",
    "中小型XS": "SMALL_XS",
    "中小型AUTO": "SMALL_AUTO",
    "特殊": "SPECIAL",
}


def normalize_model_family(value: object) -> str:
    family = str(value or "").strip()
    return MODEL_FAMILY_ALIASES.get(family, family)


def production_group_for_family(value: object) -> str:
    return PRODUCTION_GROUP_BY_FAMILY.get(normalize_model_family(value), "")


def are_production_families_compatible(source: object, target: object) -> bool:
    source_group = production_group_for_family(source)
    target_group = production_group_for_family(target)
    return bool(source_group and target_group and source_group == target_group)
