from pathlib import Path


def test_repair_catalog_route_is_a_key_protected_v8_projection():
    source = (Path(__file__).parents[1] / "api" / "routes" / "repair_catalog.py").read_text(encoding="utf-8")
    assert 'alias="modelName"' in source
    assert 'X-V8-API-KEY' in source
    assert 'find_repair_model_components(model_name)' in source
    assert '"positionCode": row["position_code"]' in source
    assert '"serialPrefix": row["position_code"]' in source
    assert '"materialCode": ""' in source
    assert 'f"V8-{row[\'position_code\']}"' not in source
