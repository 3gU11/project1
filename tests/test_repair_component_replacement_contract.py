from pathlib import Path


def test_repair_component_replacement_is_a_key_protected_idempotent_write_api():
    root = Path(__file__).parents[1]
    route = (root / "api" / "routes" / "repair_component_replacements.py").read_text(encoding="utf-8")
    crud = (root / "crud" / "repair_component_replacements.py").read_text(encoding="utf-8")

    assert '@router.post("")' in route
    assert 'alias="X-V8-API-KEY"' in route
    assert "apply_component_replacements" in route
    assert "idempotencyKey" in route
    assert "repair_component_replacement_events" in crud
    assert "FOR UPDATE" in crud
    assert "machine_component_bindings" in crud
    assert "REPAIR_REPLACED_PENDING_EVIDENCE" in crud
