import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import auth, dealer_orders


class DealerOrderAttachmentRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(dealer_orders.router, prefix="/api/v1/dealer-orders")
        app.dependency_overrides[auth.get_current_user_context] = lambda: {"username": "qa", "role": "supervisor"}
        self.permissions = patch.object(auth, "get_role_permissions", return_value=["DEALER_ORDER_REVIEW"])
        self.permissions.start()
        self.client = TestClient(app)
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "合同.pdf"
        self.file.write_bytes(b"%PDF-1.7\nlocal")
        self.view = {
            "id": "att-1",
            "orderNo": "ORDER-1",
            "contractId": "HT2026-001",
            "fileName": "合同.pdf",
            "mimeType": "application/pdf",
            "size": self.file.stat().st_size,
            "sha256": "a" * 64,
            "state": "synced",
            "syncedAt": "2026-10-24 09:00:00",
            "downloadUrl": "/api/v1/dealer-orders/ORDER-1/attachments/att-1/download",
            "previewUrl": "/api/v1/dealer-orders/ORDER-1/attachments/att-1/preview",
        }

    def tearDown(self):
        self.permissions.stop()
        self.client.close()
        self.tmp.cleanup()

    def test_lists_local_attachments_for_an_order(self):
        with patch.object(dealer_orders, "list_local_order_attachments", return_value=[self.view]):
            response = self.client.get("/api/v1/dealer-orders/ORDER-1/attachments")
        self.assertEqual(200, response.status_code)
        self.assertEqual("ORDER-1", response.json()["orderNo"])
        self.assertEqual("合同.pdf", response.json()["data"][0]["fileName"])

    def test_download_returns_local_file_and_404_when_missing(self):
        with patch.object(dealer_orders, "find_local_order_attachment", return_value={
            **self.view, "absolutePath": str(self.file),
        }):
            response = self.client.get("/api/v1/dealer-orders/ORDER-1/attachments/att-1/download")
        self.assertEqual(200, response.status_code)
        self.assertEqual(b"%PDF-1.7\nlocal", response.content)
        self.assertEqual("application/pdf", response.headers["content-type"])

        with patch.object(dealer_orders, "find_local_order_attachment", return_value=None):
            response = self.client.get("/api/v1/dealer-orders/ORDER-1/attachments/missing/download")
        self.assertEqual(404, response.status_code)

    def test_sync_pulls_from_cloud_for_the_order(self):
        with patch.object(dealer_orders, "sync_cloud_order_attachments", return_value={
            "orders": 1, "synced": 1, "skipped": 0, "failed": 0, "errors": [],
        }) as sync_mock, patch.object(dealer_orders, "append_audit_log"):
            response = self.client.post("/api/v1/dealer-orders/ORDER-1/attachments/sync")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.json()["synced"])
        sync_mock.assert_called_once_with([{"order_no": "ORDER-1", "updated_at": ""}])
