import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import create_access_token


client = TestClient(app)


def auth_headers():
    token = create_access_token(subject="boss_tester", extra={"role": "Boss", "name": "老板"})
    return {"Authorization": f"Bearer {token}"}


def test_contract_preview_returns_data_url_for_pdf(monkeypatch, tmp_path):
    import api.routes.planning as planning_route

    pdf_file = tmp_path / "demo.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")

    monkeypatch.setattr(planning_route, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        planning_route,
        "get_contract_files",
        lambda contract_id: pd.DataFrame(
            [
                {
                    "contract_id": contract_id,
                    "file_name": "demo.pdf",
                    "file_path": "demo.pdf",
                }
            ]
        ),
    )

    resp = client.get(
        "/api/v1/planning/contract/C-001/files/demo.pdf/preview",
        headers=auth_headers(),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "url"
    assert data["ext"] == ".pdf"
    assert data["url"].startswith("data:application/pdf;base64,")


def test_contract_preview_returns_404_when_file_missing(monkeypatch, tmp_path):
    import api.routes.planning as planning_route

    monkeypatch.setattr(planning_route, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        planning_route,
        "get_contract_files",
        lambda contract_id: pd.DataFrame(
            [
                {
                    "contract_id": contract_id,
                    "file_name": "missing.pdf",
                    "file_path": "missing.pdf",
                }
            ]
        ),
    )

    resp = client.get(
        "/api/v1/planning/contract/C-002/files/missing.pdf/preview",
        headers=auth_headers(),
    )

    assert resp.status_code == 404

