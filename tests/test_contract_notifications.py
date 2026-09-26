import os
import unittest
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routes import notifications
from api.routes.auth import get_current_user_context
from crud.contract_notifications import _snapshot, record_converted, record_created
from database import get_engine


class ContractNotificationTests(unittest.TestCase):
    def test_snapshot_aggregates_multi_model_contract(self):
        snapshot = _snapshot([
            {"客户名": "客户甲", "代理商": "代理乙", "机型": "FR-500", "排产数量": 2, "要求交期": "2026-10-01"},
            {"客户名": "客户甲", "代理商": "代理乙", "机型": "FR-600", "排产数量": 1, "要求交期": "2026-10-01"},
        ])
        self.assertEqual(snapshot["total"], 3)
        self.assertEqual(snapshot["models"], [
            {"model": "FR-500", "quantity": 2}, {"model": "FR-600", "quantity": 1},
        ])

    def test_non_boss_cannot_read_or_mark_messages(self):
        app = FastAPI()
        app.include_router(notifications.router, prefix="/notifications")
        app.dependency_overrides[get_current_user_context] = lambda: {"username": "sales", "role": "Sales"}
        with TestClient(app) as client:
            self.assertEqual(client.get("/notifications").status_code, 403)
            self.assertEqual(client.get("/notifications/unread-count").status_code, 403)
            self.assertEqual(client.post("/notifications/C1/read", json={"version": 1}).status_code, 403)
            self.assertEqual(client.post("/notifications/read-all", json={}).status_code, 403)

    @unittest.skipUnless(os.getenv("RUN_NOTIFICATION_DB_TESTS") == "1", "requires local migrated MySQL")
    def test_created_converted_and_replayed_version(self):
        cid = "NOTIFY-TEST-" + uuid.uuid4().hex[:12]
        row = {"客户名": "测试客户", "代理商": "", "机型": "FR-500", "排产数量": 2, "要求交期": "2026-10-01"}
        engine = get_engine()
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                record_created(conn, {cid: [row]}, "sales")
                record_created(conn, {cid: [row]}, "sales")
                self.assertEqual(conn.execute(text("SELECT version FROM contract_notifications WHERE contract_id=:cid"), {"cid": cid}).scalar_one(), 1)
                record_converted(conn, {cid: [row]}, "SO-TEST", "boss")
                record_converted(conn, {cid: [row]}, "SO-TEST", "boss")
                result = conn.execute(text("SELECT version, order_id, created_snapshot, converted_snapshot FROM contract_notifications WHERE contract_id=:cid"), {"cid": cid}).one()
                self.assertEqual((result.version, result.order_id), (2, "SO-TEST"))
                self.assertIsNotNone(result.created_snapshot)
                self.assertIsNotNone(result.converted_snapshot)
            finally:
                transaction.rollback()

    @unittest.skipUnless(os.getenv("RUN_NOTIFICATION_DB_TESTS") == "1", "requires local migrated MySQL")
    def test_legacy_contract_converts_without_fabricated_creation(self):
        cid = "NOTIFY-LEGACY-" + uuid.uuid4().hex[:12]
        row = {"客户名": "旧客户", "机型": "FR-500", "排产数量": 1}
        with get_engine().connect() as conn:
            transaction = conn.begin()
            try:
                record_converted(conn, {cid: [row]}, "SO-OLD", "boss")
                result = conn.execute(text("SELECT version, created_at, created_snapshot, order_id FROM contract_notifications WHERE contract_id=:cid"), {"cid": cid}).one()
                self.assertEqual((result.version, result.created_at, result.created_snapshot, result.order_id), (1, None, None, "SO-OLD"))
            finally:
                transaction.rollback()
