"""经销商订单「一键取消」级联内核的 sqlite 单测。

覆盖：
1) 预览阻止已出库/已发货机台；
2) 库存现货 + 在产机台混合取消后 finished_goods_data / units / sales_orders /
   factory_plan / dealer_orders / 可选排产表 的状态与云端回传事件；
3) 重复调用幂等；
4) factory_pending 阻止；
5) 无合同、仅 approved 行的订单也能取消；
6) 旧行为回归：合同取消联动经销商订单（cancel_dealer_orders_for_contracts）不变。

只使用 sqlite 内存库，不连接真实 MySQL；不依赖 crud.workflows（编排层不在本测试范围）。
"""
import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, text

from crud import dealer_order_cancel, dealer_orders

NOW_VALUE = "2026-11-12 10:00:00"

DDL_STATEMENTS = [
    """
    CREATE TABLE dealer_orders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_no TEXT NOT NULL,
      line_no INTEGER NOT NULL DEFAULT 1,
      dealer_id TEXT DEFAULT '',
      dealer_name TEXT DEFAULT '',
      customer_name TEXT DEFAULT '',
      model TEXT DEFAULT '',
      batch_no TEXT DEFAULT '',
      inventory_type TEXT DEFAULT '',
      quantity INTEGER NOT NULL DEFAULT 1,
      approved_qty INTEGER NOT NULL DEFAULT 0,
      allocated_qty INTEGER NOT NULL DEFAULT 0,
      factory_pending INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending',
      reviewed_at TEXT NULL,
      reviewed_by TEXT DEFAULT '',
      contract_no TEXT DEFAULT '',
      v7_order_no TEXT DEFAULT '',
      review_note TEXT,
      updated_at TEXT
    )
    """,
    """
    CREATE TABLE factory_plan (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      `合同号` TEXT DEFAULT '',
      `机型` TEXT DEFAULT '',
      `订单号` TEXT DEFAULT '',
      `状态` TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE sales_orders (
      `订单号` TEXT PRIMARY KEY,
      status TEXT,
      delete_reason TEXT,
      row_version INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE finished_goods_data (
      `流水号` TEXT PRIMARY KEY,
      `批次号` TEXT DEFAULT '',
      `机型` TEXT DEFAULT '',
      `状态` TEXT DEFAULT '',
      `更新时间` TEXT NULL,
      `占用订单号` TEXT DEFAULT '',
      `客户` TEXT DEFAULT '',
      `代理商` TEXT DEFAULT '',
      `合同号` TEXT DEFAULT '',
      `Location_Code` TEXT DEFAULT '',
      row_version INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE batches (
      batch_id TEXT PRIMARY KEY,
      batch_code TEXT DEFAULT '',
      status TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE units (
      unit_id TEXT PRIMARY KEY,
      batch_id TEXT,
      serial_no TEXT,
      forecast_serial_no TEXT,
      model_type TEXT,
      status TEXT,
      sales_id TEXT,
      contract_no TEXT,
      customer TEXT,
      dealer_name TEXT,
      due_date TEXT,
      order_remark TEXT,
      is_locked INTEGER NOT NULL DEFAULT 0,
      locked_by TEXT,
      locked_at TEXT,
      updated_at TEXT
    )
    """,
    """
    CREATE TABLE production_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      contract_no TEXT DEFAULT '',
      status TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE rush_order_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      contract_no TEXT DEFAULT '',
      status TEXT DEFAULT '',
      updated_by TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE production_history_ledger (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      contract_no TEXT DEFAULT '',
      status TEXT DEFAULT '',
      completed_at TEXT NULL
    )
    """,
    """
    CREATE TABLE cloud_sync_outbox (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT,
      event_type TEXT,
      biz_key TEXT,
      payload_json TEXT,
      status TEXT DEFAULT 'pending',
      retry_count INTEGER DEFAULT 0,
      last_error TEXT,
      next_retry_at TEXT,
      updated_at TEXT
    )
    """,
]


def build_sqlite_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _register_functions(conn, _record):
        conn.create_function("NOW", 0, lambda: NOW_VALUE)

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _strip_mysql_locks(conn, cursor, statement, parameters, context, executemany):
        return statement.replace("FOR UPDATE", ""), parameters

    with engine.begin() as conn:
        for ddl in DDL_STATEMENTS:
            conn.execute(text(ddl))
    return engine


def fake_insert_cloud_sync_event(conn, event_id, event_type, biz_key, payload_json):
    """替代 MySQL ON DUPLICATE KEY 的入队实现，仍写调用方事务连接，保证同事务可验证。"""
    conn.execute(
        text(
            "INSERT INTO cloud_sync_outbox (event_id, event_type, biz_key, payload_json, status) "
            "VALUES (:event_id, :event_type, :biz_key, :payload_json, 'pending')"
        ),
        {
            "event_id": event_id,
            "event_type": event_type,
            "biz_key": biz_key,
            "payload_json": payload_json,
        },
    )


class SqliteCase(unittest.TestCase):
    def setUp(self):
        self.engine = build_sqlite_engine()
        self.addCleanup(self.engine.dispose)
        self.patches = [
            patch.object(dealer_order_cancel, "get_engine", return_value=self.engine),
            patch.object(
                dealer_orders,
                "insert_cloud_sync_event",
                side_effect=fake_insert_cloud_sync_event,
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    # ------------------------------------------------------------------ helpers
    def sql(self, query, params=None):
        with self.engine.begin() as conn:
            result = conn.execute(text(query), params or {})
            return result.fetchall() if result.returns_rows else []

    def scalar(self, query, params=None):
        rows = self.sql(query, params)
        return rows[0][0] if rows else None

    def preview(self, order_no):
        return dealer_order_cancel.preview_dealer_order_cancel(order_no)

    def execute(self, order_no, operator="tester", reason="客户不要了"):
        with self.engine.begin() as conn:
            return dealer_order_cancel.execute_dealer_order_cancel(
                conn, order_no, operator, reason
            )

    def outbox_events(self):
        rows = self.sql(
            "SELECT event_type, biz_key, payload_json, status FROM cloud_sync_outbox ORDER BY id"
        )
        return [
            (event_type, biz_key, json.loads(payload_json or "{}"), status)
            for event_type, biz_key, payload_json, status in rows
        ]

    def insert_order_line(self, order_no, line_no=1, status="approved", **extra):
        columns = {"order_no": order_no, "line_no": line_no, "status": status, **extra}
        names = ", ".join(columns)
        params = ", ".join(f":{name}" for name in columns)
        self.sql(f"INSERT INTO dealer_orders ({names}) VALUES ({params})", columns)

    def insert_factory_plan(self, contract_no, status="已规划", model="M1", order_id=""):
        self.sql(
            "INSERT INTO factory_plan (`合同号`, `机型`, `订单号`, `状态`) "
            "VALUES (:contract_no, :model, :order_id, :status)",
            {
                "contract_no": contract_no,
                "model": model,
                "order_id": order_id,
                "status": status,
            },
        )

    def insert_sales_order(self, order_no, status="allocated"):
        self.sql(
            "INSERT INTO sales_orders (`订单号`, status) VALUES (:order_no, :status)",
            {"order_no": order_no, "status": status},
        )

    def insert_machine(
        self,
        serial_no,
        status="待发货",
        order_id="",
        contract_no="",
        location_code="",
        model="M1",
    ):
        self.sql(
            "INSERT INTO finished_goods_data "
            "(`流水号`, `机型`, `状态`, `占用订单号`, `合同号`, `Location_Code`) "
            "VALUES (:serial_no, :model, :status, :order_id, :contract_no, :location_code)",
            {
                "serial_no": serial_no,
                "model": model,
                "status": status,
                "order_id": order_id,
                "contract_no": contract_no,
                "location_code": location_code,
            },
        )

    def insert_batch(self, batch_id, status="In_Production", batch_code=""):
        self.sql(
            "INSERT INTO batches (batch_id, batch_code, status) "
            "VALUES (:batch_id, :batch_code, :status)",
            {"batch_id": batch_id, "batch_code": batch_code or batch_id, "status": status},
        )

    def insert_unit(self, serial_no, batch_id="B1", **extra):
        columns = {
            "unit_id": f"U-{serial_no}",
            "batch_id": batch_id,
            "serial_no": serial_no,
            "forecast_serial_no": "",
            "model_type": "M1",
            "status": "In_Production",
            **extra,
        }
        names = ", ".join(columns)
        params = ", ".join(f":{name}" for name in columns)
        self.sql(f"INSERT INTO units ({names}) VALUES ({params})", columns)

    def insert_outbox_event(self, event_type, biz_key, status="pending"):
        self.sql(
            "INSERT INTO cloud_sync_outbox "
            "(event_id, event_type, biz_key, payload_json, status) "
            "VALUES (:event_id, :event_type, :biz_key, :payload_json, :status)",
            {
                "event_id": f"old-{event_type}-{biz_key}",
                "event_type": event_type,
                "biz_key": biz_key,
                "payload_json": json.dumps({"order_no": biz_key}, ensure_ascii=False),
                "status": status,
            },
        )

    def prepare_mixed_chain(self):
        """DO-MIX：合同 HT1 → 销售订单 V7-1，一台库存现货 + 一台在产；另有无关键 DO-OTHER。"""
        self.insert_order_line(
            "DO-MIX",
            1,
            "approved",
            contract_no="HT1",
            v7_order_no="V7-1",
            model="M1",
            quantity=2,
            allocated_qty=2,
        )
        self.insert_factory_plan("HT1", "已规划", model="M1", order_id="V7-1")
        self.insert_sales_order("V7-1", "allocated")
        self.insert_machine("S-STOCK", "待发货", "V7-1", "HT1", "A01")
        self.insert_machine("S-PROD", "待发货", "V7-1", "HT1", "")
        self.insert_batch("B1", "In_Production")
        self.insert_unit(
            "S-PROD",
            "B1",
            status="In_Production",
            sales_id="V7-1",
            contract_no="HT1",
            customer="客户A",
            dealer_name="经销商A",
            due_date="2026-12-01",
            order_remark="加高",
            is_locked=1,
            locked_by="locker",
            locked_at="2026-11-01 08:00:00",
        )
        self.sql(
            "INSERT INTO production_queue (contract_no, status) "
            "VALUES ('HT1', 'Waiting'), ('HT2', 'Waiting')"
        )
        self.sql(
            "INSERT INTO rush_order_queue (contract_no, status, updated_by) "
            "VALUES ('HT1', 'pending', ''), ('HT2', 'pending', '')"
        )
        self.sql(
            "INSERT INTO production_history_ledger (contract_no, status) "
            "VALUES ('HT1', 'In_Production'), ('HT2', 'In_Production')"
        )
        # 无关订单链：取消 DO-MIX 时一行一机都不能被牵连。
        self.insert_order_line(
            "DO-OTHER", 1, "approved", contract_no="HT2", v7_order_no="V7-2", model="M1"
        )
        self.insert_factory_plan("HT2", "已规划", model="M1", order_id="V7-2")
        self.insert_sales_order("V7-2", "allocated")
        self.insert_machine("S-OTHER", "待发货", "V7-2", "HT2", "A02")
        self.insert_unit(
            "S-OTHER",
            "B1",
            status="In_Production",
            sales_id="V7-2",
            contract_no="HT2",
        )


class PreviewTests(SqliteCase):
    def test_preview_blocks_shipped_machines_with_serial_and_hint(self):
        self.insert_order_line(
            "DO-SHIP",
            1,
            "allocated",
            contract_no="HT-S",
            v7_order_no="V7-S",
            allocated_qty=1,
        )
        self.insert_factory_plan("HT-S", "已规划", order_id="V7-S")
        self.insert_sales_order("V7-S", "ready")
        # 已出库机台（占用订单号命中）与「库存中但落在客户仓」的已发货机台（合同号命中）。
        self.insert_machine("S-OUT", "已出库", "V7-S", "HT-S")
        self.insert_machine("S-DG", "库存中", "", "HT-S", "DG-WH")

        preview = self.preview("DO-SHIP")

        self.assertFalse(preview["cancellable"])
        self.assertEqual(preview["status"], "allocated")
        self.assertEqual(preview["order_no"], "DO-SHIP")
        self.assertEqual(preview["lines"], 1)
        self.assertEqual(set(preview["shipped_machines"]), {"S-OUT", "S-DG"})
        blocker_text = "；".join(preview["blockers"])
        self.assertIn("S-OUT", blocker_text)
        self.assertIn("S-DG", blocker_text)
        self.assertIn("发货复核", blocker_text)
        # 已出库机台不计入可释放机台。
        self.assertEqual(preview["machines"]["total"], 0)

    def test_preview_reports_mixed_stock_and_production_machines(self):
        self.prepare_mixed_chain()

        preview = self.preview("DO-MIX")

        self.assertTrue(preview["cancellable"], preview["blockers"])
        self.assertEqual(preview["status"], "approved")
        self.assertEqual(preview["contracts"], ["HT1"])
        self.assertEqual(preview["sales_orders"], ["V7-1"])
        self.assertEqual(preview["machines"]["total"], 2)
        self.assertEqual(preview["machines"]["stock"], 1)
        self.assertEqual(preview["machines"]["production"], 1)
        self.assertEqual(preview["machines"]["serials"], ["S-PROD", "S-STOCK"])
        self.assertEqual(preview["shipped_machines"], [])
        self.assertEqual(preview["lines"], 1)

    def test_preview_pending_order_suggests_reject(self):
        self.insert_order_line("DO-PENDING", 1, "pending")

        preview = self.preview("DO-PENDING")

        self.assertFalse(preview["cancellable"])
        self.assertTrue(any("驳回" in blocker for blocker in preview["blockers"]))

    def test_preview_cancelled_order_is_idempotent(self):
        self.insert_order_line("DO-CANCELLED", 1, "cancelled")

        preview = self.preview("DO-CANCELLED")

        self.assertEqual(preview["status"], "cancelled")
        self.assertFalse(preview["cancellable"])
        self.assertEqual(preview["blockers"], [])
        self.assertTrue(any("已取消" in warning for warning in preview["warnings"]))

    def test_preview_completed_order_is_blocked(self):
        self.insert_order_line("DO-DONE", 1, "completed")

        preview = self.preview("DO-DONE")

        self.assertFalse(preview["cancellable"])
        self.assertTrue(any("已完成" in blocker for blocker in preview["blockers"]))

    def test_preview_missing_order_raises(self):
        with self.assertRaises(ValueError):
            self.preview("DO-NOT-EXIST")


class ExecuteCascadeTests(SqliteCase):
    def test_execute_releases_stock_and_production_machines_and_cascades(self):
        self.prepare_mixed_chain()
        self.insert_outbox_event("dealer_order_allocated", "DO-MIX")

        result = self.execute("DO-MIX", operator="tester", reason="客户不要了")

        self.assertEqual(
            set(result),
            {
                "status",
                "released_serials",
                "stock",
                "production",
                "contracts",
                "sales_orders",
                "dealer_lines",
                "cloud_event",
                "warnings",
            },
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["released_serials"], ["S-PROD", "S-STOCK"])
        self.assertEqual(result["stock"], 1)
        self.assertEqual(result["production"], 1)
        self.assertEqual(result["contracts"], ["HT1"])
        self.assertEqual(result["sales_orders"], ["V7-1"])
        self.assertEqual(result["dealer_lines"], 1)
        self.assertEqual(result["cloud_event"]["event_type"], "dealer_order_cancelled")
        self.assertEqual(result["warnings"], [])

        # finished_goods_data：库存现货回到库位，在产机台回待入库，占用字段清空且版本自增。
        self.assertEqual(
            self.sql(
                "SELECT `状态`, `占用订单号`, `客户`, `代理商`, `合同号`, row_version "
                "FROM finished_goods_data WHERE `流水号`='S-STOCK'"
            ),
            [("库存中（A01）", "", "", "", "", 2)],
        )
        self.assertEqual(
            self.sql(
                "SELECT `状态`, `占用订单号`, row_version FROM finished_goods_data "
                "WHERE `流水号`='S-PROD'"
            ),
            [("待入库", "", 2)],
        )

        # units：合同/客户/配货占用全部释放。
        self.assertEqual(
            self.sql(
                "SELECT contract_no, customer, dealer_name, sales_id, due_date, "
                "order_remark, is_locked, locked_by, locked_at FROM units "
                "WHERE serial_no='S-PROD'"
            ),
            [(None, None, None, None, None, None, 0, None, None)],
        )

        # 合同取消 + 订单号解绑；销售订单软删除。
        self.assertEqual(
            self.sql(
                "SELECT `状态`, `订单号` FROM factory_plan WHERE `合同号`='HT1'"
            ),
            [("已取消", None)],
        )
        self.assertEqual(
            self.sql(
                "SELECT status, delete_reason, row_version FROM sales_orders WHERE `订单号`='V7-1'"
            ),
            [("deleted", "经销商订单 DO-MIX 取消：客户不要了", 2)],
        )

        # 经销商订单整单取消。
        self.assertEqual(
            self.sql(
                "SELECT status, factory_pending, allocated_qty, reviewed_at, reviewed_by, "
                "review_note FROM dealer_orders WHERE order_no='DO-MIX'"
            ),
            [("cancelled", 0, 0, NOW_VALUE, "tester", "客户不要了")],
        )

        # 可选排产表按合同清理，且不影响别的合同。
        self.assertEqual(
            self.sql("SELECT contract_no FROM production_queue ORDER BY contract_no"),
            [("HT2",)],
        )
        self.assertEqual(
            self.sql(
                "SELECT contract_no, status, updated_by FROM rush_order_queue ORDER BY contract_no"
            ),
            [("HT1", "deleted", "tester"), ("HT2", "pending", "")],
        )
        self.assertEqual(
            self.sql(
                "SELECT contract_no, status FROM production_history_ledger ORDER BY contract_no"
            ),
            [("HT1", "Cancelled"), ("HT2", "In_Production")],
        )

        # 云端回传：旧 pending 事件被作废，再入队整单取消事件（不带 line_nos）。
        events = self.outbox_events()
        self.assertEqual(len(events), 2)
        old_type, old_key, _, old_status = events[0]
        self.assertEqual((old_type, old_key, old_status), ("dealer_order_allocated", "DO-MIX", "superseded"))
        event_type, biz_key, payload, event_status = events[1]
        self.assertEqual(event_type, "dealer_order_cancelled")
        self.assertEqual(biz_key, "DO-MIX")
        self.assertEqual(event_status, "pending")
        self.assertEqual(payload["order_no"], "DO-MIX")
        self.assertEqual(payload["contract_no"], "HT1")
        self.assertEqual(payload["operator"], "tester")
        self.assertEqual(payload["note"], "客户不要了")
        self.assertNotIn("line_nos", payload)

    def test_execute_does_not_touch_other_order_chain(self):
        self.prepare_mixed_chain()

        self.execute("DO-MIX")

        self.assertEqual(
            self.sql(
                "SELECT status, allocated_qty, reviewed_by FROM dealer_orders "
                "WHERE order_no='DO-OTHER'"
            ),
            [("approved", 0, "")],
        )
        self.assertEqual(
            self.sql("SELECT `状态`, `订单号` FROM factory_plan WHERE `合同号`='HT2'"),
            [("已规划", "V7-2")],
        )
        self.assertEqual(
            self.sql("SELECT status FROM sales_orders WHERE `订单号`='V7-2'"),
            [("allocated",)],
        )
        self.assertEqual(
            self.sql(
                "SELECT `状态`, `占用订单号`, `合同号`, row_version FROM finished_goods_data "
                "WHERE `流水号`='S-OTHER'"
            ),
            [("待发货", "V7-2", "HT2", 1)],
        )
        self.assertEqual(
            self.sql("SELECT sales_id, contract_no FROM units WHERE serial_no='S-OTHER'"),
            [("V7-2", "HT2")],
        )

    def test_repeated_execute_is_idempotent(self):
        self.prepare_mixed_chain()
        self.execute("DO-MIX")
        event_count = len(self.outbox_events())

        second = self.execute("DO-MIX")

        self.assertEqual(second["status"], "cancelled")
        self.assertEqual(second["released_serials"], [])
        self.assertEqual(second["stock"], 0)
        self.assertEqual(second["production"], 0)
        self.assertEqual(second["dealer_lines"], 0)
        self.assertIsNone(second["cloud_event"])
        self.assertTrue(any("已取消" in warning for warning in second["warnings"]))
        self.assertEqual(len(self.outbox_events()), event_count)
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-MIX'"),
            [("cancelled",)],
        )
        # 重复调用不会再次改写机台状态/版本。
        self.assertEqual(
            self.scalar(
                "SELECT row_version FROM finished_goods_data WHERE `流水号`='S-STOCK'"
            ),
            2,
        )

    def test_factory_pending_blocks_preview_and_execute(self):
        self.insert_order_line(
            "DO-FROZEN",
            1,
            "approved",
            contract_no="HT-F",
            v7_order_no="V7-F",
            factory_pending=1,
        )
        self.insert_factory_plan("HT-F", "已规划", order_id="V7-F")
        self.insert_sales_order("V7-F", "allocated")
        self.insert_machine("S-FROZEN", "待发货", "V7-F", "HT-F")

        preview = self.preview("DO-FROZEN")
        self.assertFalse(preview["cancellable"])
        self.assertTrue(any("复审" in blocker for blocker in preview["blockers"]))

        with self.assertRaises(ValueError):
            self.execute("DO-FROZEN")

        self.assertEqual(
            self.sql("SELECT status, factory_pending FROM dealer_orders WHERE order_no='DO-FROZEN'"),
            [("approved", 1)],
        )
        self.assertEqual(
            self.sql(
                "SELECT `状态`, `占用订单号` FROM finished_goods_data WHERE `流水号`='S-FROZEN'"
            ),
            [("待发货", "V7-F")],
        )
        self.assertEqual(self.outbox_events(), [])

    def test_execute_without_contract_still_cancels_order(self):
        self.insert_order_line("DO-NOCONTRACT", 1, "approved")

        preview = self.preview("DO-NOCONTRACT")
        self.assertTrue(preview["cancellable"], preview["blockers"])
        self.assertEqual(preview["contracts"], [])
        self.assertTrue(any("合同" in warning for warning in preview["warnings"]))

        result = self.execute("DO-NOCONTRACT", operator="ops", reason="客户退单")

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["released_serials"], [])
        self.assertEqual(result["contracts"], [])
        self.assertEqual(result["sales_orders"], [])
        self.assertEqual(result["dealer_lines"], 1)
        self.assertEqual(
            self.sql(
                "SELECT status, factory_pending, allocated_qty, reviewed_by, review_note "
                "FROM dealer_orders WHERE order_no='DO-NOCONTRACT'"
            ),
            [("cancelled", 0, 0, "ops", "客户退单")],
        )
        events = self.outbox_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "dealer_order_cancelled")
        self.assertEqual(events[0][1], "DO-NOCONTRACT")
        self.assertEqual(events[0][2]["contract_no"], "")

    def test_execute_rejects_completed_order(self):
        self.insert_order_line("DO-COMPLETE", 1, "completed")

        with self.assertRaises(ValueError):
            self.execute("DO-COMPLETE")

        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-COMPLETE'"),
            [("completed",)],
        )
        self.assertEqual(self.outbox_events(), [])

    def test_execute_refuses_shipped_machine(self):
        self.insert_order_line(
            "DO-SHIPPED", 1, "allocated", contract_no="HT-X", v7_order_no="V7-X"
        )
        self.insert_factory_plan("HT-X", "已规划", order_id="V7-X")
        self.insert_sales_order("V7-X", "allocated")
        self.insert_machine("S-SHIPPED", "已出库", "V7-X", "HT-X")

        with self.assertRaises(ValueError) as caught:
            self.execute("DO-SHIPPED")

        self.assertIn("S-SHIPPED", str(caught.exception))
        self.assertEqual(
            self.sql(
                "SELECT `状态`, `占用订单号` FROM finished_goods_data WHERE `流水号`='S-SHIPPED'"
            ),
            [("已出库", "V7-X")],
        )
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-SHIPPED'"),
            [("allocated",)],
        )
        self.assertEqual(self.outbox_events(), [])


class ExistingBehaviourRegressionTests(SqliteCase):
    def test_contract_cancel_link_to_dealer_orders_still_works(self):
        """旧入口 cancel_dealer_orders_for_contracts 的行为保持不变。"""
        self.insert_factory_plan("HT-OLD", "已取消")
        self.insert_order_line("DO-OLD", 1, "contracted", contract_no="HT-OLD")

        with patch.object(dealer_orders, "get_engine", return_value=self.engine):
            with self.engine.begin() as conn:
                result = dealer_orders.cancel_dealer_orders_for_contracts(
                    conn, ["HT-OLD"], operator="legacy", reason="合同取消"
                )

        self.assertEqual(result["orders"], ["DO-OLD"])
        self.assertEqual(result["lines"], 1)
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-OLD'"),
            [("cancelled",)],
        )
        events = self.outbox_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "dealer_order_cancelled")
        self.assertEqual(events[0][1], "DO-OLD")
        self.assertEqual(events[0][2]["note"], "合同取消")


if __name__ == "__main__":
    unittest.main()
