from pathlib import Path


def test_repair_identity_accepts_caigou_base_url_without_a_trailing_slash():
    source = (Path(__file__).parents[1] / "api" / "routes" / "repair_identity.py").read_text(encoding="utf-8")
    assert '@router.get("")' in source
    assert '@router.get("/")' in source
