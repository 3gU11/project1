import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import auth, dealer_orders


class SyncChannelRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(dealer_orders.router, prefix="/api/v1/dealer-orders")
        app.dependency_overrides[auth.get_current_user_context] = lambda: {
            "username": "qa",
            "role": "supervisor",
        }
        self.permissions = patch.object(
            auth, "get_role_permissions", return_value=["DEALER_ORDER_REVIEW"]
        )
        self.permissions.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.permissions.stop()
        self.client.close()

    def test_sync_inventory_returns_real_counts(self):
        payload = {"local_rows": 101, "pushed_rows": 99, "model_rows": 31}
        with (
            patch.object(dealer_orders, "sync_wechat_batch_summary_to_cloud", return_value=payload) as sync_mock,
            patch.object(dealer_orders, "process_due_cloud_sync_events", return_value={}),
            patch.object(dealer_orders, "append_audit_log"),
        ):
            response = self.client.post("/api/v1/dealer-orders/sync-wechat-batch-summary")

        self.assertEqual(200, response.status_code)
        self.assertEqual(payload, response.json())
        sync_mock.assert_called_once_with(trigger="manual")

    def test_sync_channels_lists_channel_payload(self):
        expected = {
            "server_time": "2026-10-28 15:00:00",
            "channels": [
                {
                    "key": "machine-snapshot",
                    "label": "机台快照同步",
                    "state": "down",
                    "state_label": "超期未同步",
                }
            ],
        }
        with patch.object(dealer_orders, "get_sync_channels_status", return_value=expected):
            response = self.client.get("/api/v1/dealer-orders/sync-channels")

        self.assertEqual(200, response.status_code)
        self.assertEqual(expected, response.json())

    def test_manual_machine_snapshot_reports_event_status(self):
        with (
            patch("v8_sync.scheduler.run_daily", return_value={
                "status": "created",
                "event_id": "v8-repair-snapshot-20261028-abc",
            }),
            patch.object(dealer_orders, "process_due_cloud_sync_events", return_value={"processed": 1}),
            patch.object(
                dealer_orders,
                "get_cloud_sync_event_status",
                return_value={"event_id": "v8-repair-snapshot-20261028-abc", "status": "synced"},
            ),
            patch.object(dealer_orders, "append_audit_log"),
        ):
            response = self.client.post("/api/v1/dealer-orders/sync-machine-snapshot")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("created", body["status"])
        self.assertEqual("synced", body["event_status"]["status"])
        self.assertEqual("机台快照已上传", body["message"])

    def test_manual_reconcile_order_status_runs_once_and_records_heartbeat(self):
        """「立即对账」按钮：按配置窗口/上限补发，并立即处理已排队事件。"""
        summary = {
            "trigger": "manual",
            "scanned": 3,
            "enqueued": 1,
            "skipped": 2,
            "window_days": 7,
            "limit": 500,
            "events": [{"order_no": "DO-R1", "event_type": "dealer_order_contracted", "status": "contracted"}],
        }
        with (
            patch("crud.cloud_sync_outbox.reconcile_dealer_order_statuses", return_value=summary) as reconcile_mock,
            patch("crud.cloud_sync_outbox.reconcile_limit", return_value=500),
            patch("crud.cloud_sync_outbox.reconcile_window_days", return_value=7),
            patch.object(dealer_orders, "process_due_cloud_sync_events", return_value={"processed": 1}) as process_mock,
            patch.object(dealer_orders, "append_audit_log") as audit_mock,
            patch.object(dealer_orders, "record_channel_success") as heartbeat_mock,
        ):
            response = self.client.post("/api/v1/dealer-orders/reconcile-order-status")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(3, body["scanned"])
        self.assertEqual(1, body["enqueued"])
        self.assertEqual({"processed": 1}, body["processed"])
        reconcile_mock.assert_called_once_with(500, trigger="manual", window_days=7)
        process_mock.assert_called_once_with(limit=20)
        audit_mock.assert_called_once()
        heartbeat_mock.assert_called_once_with("status-callback", "manual")


if __name__ == "__main__":
    unittest.main()
