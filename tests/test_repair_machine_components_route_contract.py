"""维修系统机台零部件只读接口的契约测试（只读、密钥保护、404 语义）。"""
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_repair_machine_components_route_is_key_protected_read_only_projection():
    source = (ROOT / "api" / "routes" / "repair_machine_components.py").read_text(encoding="utf-8")

    assert '@router.get("")' in source
    assert '@router.get("/")' in source
    assert 'alias="machineNo"' in source
    assert 'alias="includeInactive"' in source
    assert 'alias="X-V8-API-KEY"' in source
    assert "REPAIR_IDENTITY_API_KEY" in source
    assert "find_repair_machine_components(machine_no" in source
    assert "HTTP_404_NOT_FOUND" in source
    # 只读：路由只做查询，不允许写库。
    assert "insert" not in source.lower()
    assert "update" not in source.lower()
    assert "delete" not in source.lower()


def test_repair_machine_components_router_is_registered():
    source = (ROOT / "api" / "main.py").read_text(encoding="utf-8")

    assert "repair_machine_components.router" in source
    assert '"/api/v1/repair-machine-components"' in source
