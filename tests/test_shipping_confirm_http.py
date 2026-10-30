from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import inventory


def test_shipping_confirm_accepts_flat_payload_without_internal_workflow(monkeypatch):
    app = FastAPI()
    app.include_router(inventory.router)
    app.dependency_overrides[inventory.get_current_user_token] = lambda: 'test-token'
    app.dependency_overrides[inventory.get_current_operator_name] = lambda: 'tester'
    app.dependency_overrides[inventory.get_current_user_context] = lambda: {'username': 'tester'}
    calls = []

    def confirm(payload, request, operator, user):
        calls.append((payload, operator, user))
        return {'message': 'ok'}

    monkeypatch.setattr(inventory, 'confirm_shipping', confirm)
    with TestClient(app) as client:
        response = client.post('/shipping/confirm', json={'serial_nos': ['SN-1'], 'expected_order_no': 'SO-1'})
        assert response.status_code == 200, response.text
        assert calls[0][0].serial_nos == ['SN-1']
        assert calls[0][0].expected_order_no == 'SO-1'
        assert client.post('/shipping/confirm', json={'serial_nos': 'SN-1'}).status_code == 422
    assert len(calls) == 1
