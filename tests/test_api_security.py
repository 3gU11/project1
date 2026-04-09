from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import create_access_token


client = TestClient(app)


def test_protected_endpoints_require_auth():
    protected_gets = [
        "/api/v1/planning/",
        "/api/v1/inventory/",
        "/api/v1/logs/transactions",
    ]
    for path in protected_gets:
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} should require auth"


def test_register_supports_inbound_role(monkeypatch):
    import api.routes.users as users_route

    monkeypatch.setattr(users_route, "user_exists", lambda username: False)
    monkeypatch.setattr(
        users_route,
        "create_pending_user",
        lambda username, password, role, name: {
            "username": username,
            "password": password,
            "role": role,
            "name": name,
            "status": "pending",
        },
    )

    payload = {
        "username": "inbound_tester",
        "password": "123456",
        "role": "Inbound",
        "name": "入库测试",
    }
    resp = client.post("/api/v1/users/register", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["role"] == "Inbound"


def test_users_list_forbidden_for_sales_role():
    token = create_access_token(subject="sales_tester", extra={"role": "Sales", "name": "销售"})
    resp = client.get("/api/v1/users/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
