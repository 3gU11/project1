"""交付信息删除：真实事务、附件边界、状态保护及接口权限。"""

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from api.routes import auth, delivery_info_uploads as routes


class DeliveryInfoDeleteTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = directory.name
        self.pending = os.path.join(self.root, "data", "delivery-info-pending")
        os.makedirs(self.pending)
        self.attachment = os.path.join(self.pending, "contract.pdf")
        with open(self.attachment, "wb") as handle:
            handle.write(b"test attachment")
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE delivery_info_uploads (id INTEGER PRIMARY KEY, status TEXT, file_path TEXT, file_name TEXT)"))
            conn.execute(text("CREATE TABLE delivery_info_upload_machines (upload_id INTEGER, serial_no TEXT)"))
            conn.execute(text("INSERT INTO delivery_info_uploads VALUES (1, 'pending', :path, 'contract.pdf')"), {"path": os.path.relpath(self.attachment, self.root)})
            conn.execute(text("INSERT INTO delivery_info_upload_machines VALUES (1, '96-08-306')"))
        for item in (
            patch.object(routes, "BASE_DIR", self.root),
            patch.object(routes, "PENDING_ROOT", self.pending),
            patch.object(routes, "get_engine", return_value=self.engine),
            patch.object(routes, "ensure_delivery_info_tables"),
        ):
            item.start()
            self.addCleanup(item.stop)
        audit_patch = patch.object(routes, "append_audit_log")
        self.audit = audit_patch.start()
        self.addCleanup(audit_patch.stop)
        permission_patch = patch.object(auth, "get_role_permissions", return_value=["QUERY", "SHIP_CONFIRM"])
        self.permissions = permission_patch.start()
        self.addCleanup(permission_patch.stop)
        app = FastAPI()
        app.include_router(routes.router, prefix="/inventory")
        app.dependency_overrides[auth.get_current_user_context] = lambda: {"username": "tester", "role": "test"}
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def delete(self, upload_id=1):
        return self.client.delete(f"/inventory/delivery-info-uploads/{upload_id}")

    def count(self, table_name="delivery_info_uploads"):
        with self.engine.connect() as conn:
            return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()

    def test_delete_removes_record_links_and_attachment_and_logs(self):
        response = self.delete()
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["deleted"])
        self.assertEqual([], response.json()["warnings"])
        self.assertEqual(0, self.count())
        self.assertEqual(0, self.count("delivery_info_upload_machines"))
        self.assertFalse(os.path.exists(self.attachment))
        self.assertEqual("删除交付信息上传", self.audit.call_args.kwargs["action_type"])
        self.assertEqual(404, self.delete().status_code)

    def test_missing_attachment_can_still_delete(self):
        os.remove(self.attachment)
        self.assertEqual(200, self.delete().status_code)
        self.assertEqual(0, self.count())

    def test_processed_record_and_attachment_are_preserved(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE delivery_info_uploads SET status='processed'"))
        self.assertEqual(409, self.delete().status_code)
        self.assertEqual(1, self.count())
        self.assertEqual(1, self.count("delivery_info_upload_machines"))
        self.assertTrue(os.path.exists(self.attachment))
        self.audit.assert_not_called()

    def test_missing_record_returns_404(self):
        self.assertEqual(404, self.delete(999).status_code)
        self.assertTrue(os.path.exists(self.attachment))

    def test_query_permission_cannot_delete(self):
        self.permissions.return_value = ["QUERY"]
        self.assertEqual(403, self.delete().status_code)
        self.assertEqual(1, self.count())
        self.assertTrue(os.path.exists(self.attachment))

    def test_path_outside_pending_directory_is_rejected(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE delivery_info_uploads SET file_path='../outside.pdf'"))
        self.assertEqual(409, self.delete().status_code)
        self.assertEqual(1, self.count())
        self.assertTrue(os.path.exists(self.attachment))

    def test_file_cleanup_failure_is_reported_after_record_deletion(self):
        with patch.object(routes.os, "remove", side_effect=PermissionError("locked")), self.assertLogs(routes.logger, level="ERROR"):
            response = self.delete()
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["warnings"])
        self.assertEqual(0, self.count())
        self.assertTrue(os.path.exists(self.attachment))

    def test_deleted_upload_cannot_be_processed(self):
        self.assertEqual(200, self.delete().status_code)
        response = self.client.post("/inventory/delivery-info-uploads/1/process", json={"serial_nos": ["96-08-306"]})
        self.assertEqual(404, response.status_code)

    def test_database_failure_keeps_record_and_attachment(self):
        from sqlalchemy import event

        def fail_delete(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("DELETE FROM delivery_info_uploads WHERE"):
                raise RuntimeError("database unavailable")

        event.listen(self.engine, "before_cursor_execute", fail_delete)
        try:
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                self.delete()
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_delete)
        self.assertEqual(1, self.count())
        self.assertEqual(1, self.count("delivery_info_upload_machines"))
        self.assertTrue(os.path.exists(self.attachment))


if __name__ == "__main__":
    unittest.main()
