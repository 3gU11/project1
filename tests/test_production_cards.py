"""Production-board cleanup for machines shipped while still on a line."""
import unittest
from unittest.mock import patch

import pandas as pd

from sqlalchemy import create_engine, event, text

from api.routes import inventory
from crud.production_cards import (
    restore_shipped_production_cards,
    retire_shipped_production_cards,
)


class ProductionCardRetireTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def functions(conn, _):
            conn.create_function("NOW", 0, lambda: "2026-10-26 15:00")

        @event.listens_for(self.engine, "before_cursor_execute", retval=True)
        def strip_locks(conn, cursor, statement, parameters, context, executemany):
            return statement.replace("FOR UPDATE", ""), parameters

        self.now = "2026-10-26 15:00"

    def create_schema(self):
        with self.engine.begin() as conn:
            for sql in [
                "CREATE TABLE units (unit_id TEXT PRIMARY KEY, batch_id TEXT, status TEXT, "
                "serial_no TEXT, forecast_serial_no TEXT, production_line_id TEXT, updated_at TEXT)",
                "CREATE TABLE batches (batch_id TEXT PRIMARY KEY, batch_code TEXT, batch_no INTEGER, "
                "status TEXT, production_line_id TEXT, updated_at TEXT)",
                "CREATE TABLE production_lines (line_id TEXT PRIMARY KEY, status TEXT, "
                "current_batch_id TEXT, updated_at TEXT)",
                "CREATE TABLE production_history_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "unit_id TEXT, status TEXT, completed_at TEXT, updated_at TEXT)",
            ]:
                conn.execute(text(sql))

    def seed_partial_batch(self):
        self.create_schema()
        with self.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO batches VALUES ('B1','07-03附加',3,'In_Production','L1','2026-07-21')"
            ))
            conn.execute(text(
                "INSERT INTO production_lines VALUES ('L1','Busy','B1','2026-07-21')"
            ))
            conn.execute(text(
                "INSERT INTO units VALUES "
                "('U1','B1','In_Production',NULL,'96-07-75','L1','2026-09-27'),"
                "('U2','B1','In_Production',NULL,'96-07-76','L1','2026-07-21')"
            ))
            conn.execute(text(
                "INSERT INTO production_history_ledger (unit_id, status, updated_at) VALUES "
                "('U1','In_Production','2026-07-21'),('U2','In_Production','2026-07-21')"
            ))

    def rows(self, sql):
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).fetchall()

    def retire(self, serials):
        with self.engine.begin() as conn:
            return retire_shipped_production_cards(conn, serials, self.now)

    def restore(self, serials):
        with self.engine.begin() as conn:
            return restore_shipped_production_cards(conn, serials, self.now)

    def test_partial_batch_retires_only_shipped_unit(self):
        self.seed_partial_batch()
        result = self.retire(["96-07-75"])

        self.assertEqual(result["unit_ids"], ["U1"])
        self.assertEqual(result["completed_batches"], [])
        self.assertEqual(
            self.rows("SELECT unit_id,status,production_line_id FROM units ORDER BY unit_id"),
            [("U1", "Completed", None), ("U2", "In_Production", "L1")],
        )
        self.assertEqual(
            self.rows("SELECT unit_id,status FROM production_history_ledger ORDER BY unit_id"),
            [("U1", "Completed"), ("U2", "In_Production")],
        )
        self.assertEqual(
            self.rows("SELECT batch_id,status FROM batches"), [("B1", "In_Production")]
        )
        self.assertEqual(
            self.rows("SELECT line_id,status,current_batch_id FROM production_lines"),
            [("L1", "Busy", "B1")],
        )

    def test_last_unit_completes_batch_and_idles_line(self):
        self.seed_partial_batch()
        result = self.retire(["96-07-75", "96-07-76"])

        self.assertEqual(result["completed_batches"], ["B1"])
        self.assertEqual(
            self.rows("SELECT unit_id,status,production_line_id FROM units ORDER BY unit_id"),
            [("U1", "Completed", None), ("U2", "Completed", None)],
        )
        self.assertEqual(
            self.rows("SELECT line_id,status,current_batch_id FROM production_lines"),
            [("L1", "Idle", None)],
        )
        self.assertEqual(self.rows("SELECT status FROM batches"), [("Completed",)])

    def test_second_retire_is_noop_and_unknown_serials_are_ignored(self):
        self.seed_partial_batch()
        self.retire(["96-07-75"])
        self.assertEqual(self.retire(["96-07-75"]), {
            "unit_ids": [], "completed_batches": [], "affected_lines": [],
        })
        self.assertEqual(self.retire(["missing"]), {
            "unit_ids": [], "completed_batches": [], "affected_lines": [],
        })

    def test_restore_returns_card_to_active_batch(self):
        self.seed_partial_batch()
        self.retire(["96-07-75"])
        result = self.restore(["96-07-75"])

        self.assertEqual(result["unit_ids"], ["U1"])
        self.assertEqual(
            self.rows("SELECT unit_id,status,production_line_id FROM units ORDER BY unit_id"),
            [("U1", "In_Production", "L1"), ("U2", "In_Production", "L1")],
        )
        self.assertEqual(
            self.rows("SELECT unit_id,status,completed_at FROM production_history_ledger ORDER BY unit_id"),
            [("U1", "In_Production", None), ("U2", "In_Production", None)],
        )

    def test_restore_leaves_completed_batch_alone(self):
        self.seed_partial_batch()
        self.retire(["96-07-75", "96-07-76"])
        self.assertEqual(
            self.restore(["96-07-75", "96-07-76"]),
            {"unit_ids": [], "affected_lines": []},
        )
        self.assertEqual(self.rows("SELECT status FROM batches"), [("Completed",)])

    def test_helper_tolerates_legacy_schema(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE units (unit_id TEXT PRIMARY KEY, status TEXT, serial_no TEXT)"
            ))
            conn.execute(text("INSERT INTO units VALUES ('U1','In_Production','96-07-75')"))
        result = self.retire(["96-07-75"])
        self.assertEqual(result["unit_ids"], ["U1"])
        self.assertEqual(self.rows("SELECT status FROM units"), [("Completed",)])


class ConfirmShippingProductionCardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def functions(conn, _):
            conn.create_function("NOW", 0, lambda: "2026-10-26 15:00")

        @event.listens_for(self.engine, "before_cursor_execute", retval=True)
        def strip_locks(conn, cursor, statement, parameters, context, executemany):
            return statement.replace("FOR UPDATE", ""), parameters

        with self.engine.begin() as conn:
            for sql in [
                "CREATE TABLE finished_goods_data (`流水号` TEXT PRIMARY KEY, `状态` TEXT, "
                "`更新时间` TEXT, `占用订单号` TEXT, `机型` TEXT, `客户` TEXT, `代理商` TEXT, "
                "`合同号` TEXT, `合同备注` TEXT, `批次号` TEXT, `预计入库时间` TEXT, `Location_Code` TEXT)",
                "CREATE TABLE units (unit_id TEXT PRIMARY KEY, batch_id TEXT, status TEXT, "
                "serial_no TEXT, forecast_serial_no TEXT, production_line_id TEXT, updated_at TEXT)",
                "CREATE TABLE batches (batch_id TEXT PRIMARY KEY, batch_no INTEGER, status TEXT, "
                "production_line_id TEXT, updated_at TEXT)",
                "CREATE TABLE production_lines (line_id TEXT PRIMARY KEY, status TEXT, "
                "current_batch_id TEXT, updated_at TEXT)",
                "CREATE TABLE production_history_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "unit_id TEXT, status TEXT, completed_at TEXT, updated_at TEXT)",
                "INSERT INTO batches VALUES ('B1',3,'In_Production','L1','2026-07-21')",
                "INSERT INTO production_lines VALUES ('L1','Busy','B1','2026-07-21')",
                "INSERT INTO units VALUES "
                "('U1','B1','In_Production',NULL,'96-07-75','L1','2026-09-27'),"
                "('U2','B1','In_Production',NULL,'96-07-76','L1','2026-07-21')",
                "INSERT INTO production_history_ledger (unit_id,status,updated_at) VALUES "
                "('U1','In_Production','2026-07-21'),('U2','In_Production','2026-07-21')",
                "INSERT INTO finished_goods_data (`流水号`,`状态`,`占用订单号`,`机型`) VALUES "
                "('96-07-75','待发货','SO-TEST','FR-1080Y'),"
                "('96-07-76','待发货','SO-TEST','FR-1080Y')",
            ]:
                conn.execute(text(sql))

        self.patches = [
            patch.object(inventory, "get_engine", return_value=self.engine),
            patch.object(inventory, "cache"),
            patch.object(inventory, "enqueue_wechat_batch_summary_sync"),
            patch.object(
                inventory,
                "get_orders",
                return_value=pd.DataFrame(columns=["订单号", "需求机型", "需求数量", "status"]),
            ),
            patch.object(inventory, "save_orders"),
            patch.object(inventory, "archive_shipped_data"),
            patch.object(inventory, "append_log"),
            patch.object(inventory, "append_audit_log"),
            patch.object(inventory, "release_completed_order_reservations", return_value=[]),
            patch.object(inventory, "sync_dealer_order_statuses_by_sales_orders", return_value=[]),
            patch.object(inventory, "enqueue_cloud_sync_event"),
        ]
        for pending in self.patches:
            pending.start()
            self.addCleanup(pending.stop)

    def rows(self, sql):
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).fetchall()

    def confirm(self, serials):
        return inventory.confirm_shipping(
            inventory.ShippingActionPayload(serial_nos=serials),
            request=None,
            current_operator="tester",
            current_user={"username": "tester"},
        )

    def test_confirm_shipping_retires_card_of_still_active_unit(self):
        self.confirm(["96-07-75"])

        self.assertEqual(
            self.rows("SELECT `流水号`,`状态` FROM finished_goods_data ORDER BY `流水号`"),
            [("96-07-75", "已出库"), ("96-07-76", "待发货")],
        )
        self.assertEqual(
            self.rows("SELECT unit_id,status,production_line_id FROM units ORDER BY unit_id"),
            [("U1", "Completed", None), ("U2", "In_Production", "L1")],
        )
        self.assertEqual(
            self.rows("SELECT unit_id,status FROM production_history_ledger ORDER BY unit_id"),
            [("U1", "Completed"), ("U2", "In_Production")],
        )
        self.assertEqual(self.rows("SELECT status FROM batches"), [("In_Production",)])
        self.assertEqual(
            self.rows("SELECT status,current_batch_id FROM production_lines"),
            [("Busy", "B1")],
        )

    def test_confirm_all_units_completes_batch_and_idles_line(self):
        self.confirm(["96-07-75", "96-07-76"])

        self.assertEqual(self.rows("SELECT status FROM batches"), [("Completed",)])
        self.assertEqual(
            self.rows("SELECT status,current_batch_id FROM production_lines"),
            [("Idle", None)],
        )
        self.assertEqual(
            self.rows("SELECT COUNT(*) FROM units WHERE status='In_Production'"), [(0,)]
        )

    def test_repeated_confirm_does_not_fail(self):
        first = self.confirm(["96-07-75"])
        second = self.confirm(["96-07-75"])
        self.assertIn("发货完成", first["message"])
        self.assertIn("已发货", second["message"])


if __name__ == "__main__":
    unittest.main()
