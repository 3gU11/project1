from fastapi.testclient import TestClient

from api.main import app


def test_sales_orders_path_serves_spa_entry():
    client = TestClient(app)

    response = client.get("/sales-orders")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_unknown_api_path_stays_404():
    client = TestClient(app)

    response = client.get("/api/v1/not-found")

    assert response.status_code == 404
