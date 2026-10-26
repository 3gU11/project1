"""合同取消联动经销商订单取消 + 状态回传取值 + 历史数据修复脚本的 sqlite 单测。"""
import importlib.util
import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event, text

from api.routes import planning
from crud import cloud_sync_outbox, dealer_orders

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_repair_script():
    path = PROJECT_ROOT / "tools" / "repair_dealer_orders_for_cancelled_contracts.py"
    spec = importlib.util.spec_from_file_location("repair_dealer_orders_for_cancelled_contracts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair_script = _load_repair_script()


DEALER_ORDERS_DDL = """
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
  review_note TEXT
)
"""

FACTORY_PLAN_DDL = """
CREATE TABLE factory_plan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  `合同号` TEXT DEFAULT '',
  `机型` TEXT DEFAULT '',
  `订单号` TEXT DEFAULT '',
  `状态` TEXT DEFAULT ''
)
"""

CLOUD_SYNC_OUTBOX_DDL = """
CREATE TABLE cloud_sync_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT,
  event_type TEXT,
  biz_key TEXT,
  payload_json TEXT,
  status TEXT DEFAULT 'pending',
  last_error TEXT,
  updated_at TEXT
)
"""


def build_sqlite_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _functions(conn, _):
        conn.create_function("NOW", 0, lambda: "2026-10-24 12:00:00")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _strip_mysql_locks(conn, cursor, statement, parameters, context, executemany):
        return statement.replace("FOR UPDATE", ""), parameters

    with engine.begin() as conn:
        for ddl in (DEALER_ORDERS_DDL, FACTORY_PLAN_DDL, CLOUD_SYNC_OUTBOX_DDL):
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

    def sql(self, query, params=None):
        with self.engine.begin() as conn:
            result = conn.execute(text(query), params or {})
            return result.fetchall() if result.returns_rows else []

    def scalar(self, query, params=None):
        rows = self.sql(query, params)
        return rows[0][0] if rows else None

    def outbox_events(self):
        rows = self.sql("SELECT event_type, biz_key, payload_json FROM cloud_sync_outbox ORDER BY id")
        return [(event_type, biz_key, json.loads(payload)) for event_type, biz_key, payload in rows]

    def insert_order_line(self, order_no, line_no, status, contract_no, **extra):
        columns = {
            "order_no": order_no,
            "line_no": line_no,
            "status": status,
            "contract_no": contract_no,
            **extra,
        }
        names = ", ".join(columns)
        params = ", ".join(f":{name}" for name in columns)
        self.sql(f"INSERT INTO dealer_orders ({names}) VALUES ({params})", columns)

    def insert_factory_plan(self, contract_no, status, model="M1", order_id=""):
        self.sql(
            "INSERT INTO factory_plan (`合同号`, `机型`, `订单号`, `状态`) "
            "VALUES (:contract_no, :model, :order_id, :status)",
            {"contract_no": contract_no, "model": model, "order_id": order_id, "status": status},
        )

    def mark_contract_cancelled(self, *contract_nos):
        for contract_no in contract_nos:
            self.insert_factory_plan(contract_no, "已取消")

    def insert_outbox_event(self, event_type, biz_key, payload=None, status="pending", last_error=None):
        self.sql(
            "INSERT INTO cloud_sync_outbox "
            "(event_id, event_type, biz_key, payload_json, status, last_error) "
            "VALUES (:event_id, :event_type, :biz_key, :payload_json, :status, :last_error)",
            {
                "event_id": f"old-{event_type}-{biz_key}",
                "event_type": event_type,
                "biz_key": biz_key,
                "payload_json": json.dumps(payload or {}, ensure_ascii=False),
                "status": status,
                "last_error": last_error,
            },
        )


class CancelDealerOrdersForContractsTests(SqliteCase):
    def setUp(self):
        super().setUp()
        self.patch_insert = patch.object(
            dealer_orders, "insert_cloud_sync_event", side_effect=fake_insert_cloud_sync_event
        )
        self.patch_insert.start()
        self.addCleanup(self.patch_insert.stop)

    def cancel(self, contract_ids, **kwargs):
        with self.engine.begin() as conn:
            return dealer_orders.cancel_dealer_orders_for_contracts(conn, contract_ids, **kwargs)

    def test_whole_order_cancel_marks_lines_and_enqueues_cancelled_event(self):
        self.mark_contract_cancelled("HT1")
        self.insert_order_line("DO1", 1, "contracted", "HT1")
        self.insert_order_line("DO1", 2, "contracted", "HT1")

        result = self.cancel(["HT1"], operator="tester", reason="合同 HT1 已取消")

        self.assertEqual(result["orders"], ["DO1"])
        self.assertEqual(result["lines"], 2)
        rows = self.sql(
            "SELECT status, factory_pending, allocated_qty, reviewed_by, review_note, reviewed_at "
            "FROM dealer_orders WHERE order_no='DO1' ORDER BY line_no"
        )
        self.assertEqual(len(rows), 2)
        for status, factory_pending, allocated_qty, reviewed_by, review_note, reviewed_at in rows:
            self.assertEqual(status, "cancelled")
            self.assertEqual(factory_pending, 0)
            self.assertEqual(allocated_qty, 0)
            self.assertEqual(reviewed_by, "tester")
            self.assertEqual(review_note, "合同 HT1 已取消")
            self.assertEqual(reviewed_at, "2026-10-24 12:00:00")

        events = self.outbox_events()
        self.assertEqual(len(events), 1)
        event_type, biz_key, payload = events[0]
        self.assertEqual(event_type, "dealer_order_cancelled")
        self.assertEqual(biz_key, "DO1")
        self.assertEqual(payload["order_no"], "DO1")
        self.assertEqual(payload["contract_no"], "HT1")
        self.assertEqual(payload["operator"], "tester")
        self.assertEqual(payload["note"], "合同 HT1 已取消")
        # 整单全部行取消时不带 line_nos
        self.assertNotIn("line_nos", payload)

    def test_partial_line_cancel_sends_line_nos(self):
        self.mark_contract_cancelled("HT1", "HT4")
        self.insert_factory_plan("HT3", "待规划")
        self.insert_order_line("DO2", 1, "contracted", "HT1")
        self.insert_order_line("DO2", 2, "contracted", "HT3")
        self.insert_order_line("DO2", 3, "approved", "HT1,HT4")

        self.cancel("HT1")

        self.assertEqual(
            self.sql("SELECT line_no, status FROM dealer_orders WHERE order_no='DO2' ORDER BY line_no"),
            [(1, "cancelled"), (2, "contracted"), (3, "cancelled")],
        )
        events = self.outbox_events()
        self.assertEqual(len(events), 1)
        _, _, payload = events[0]
        self.assertEqual(payload["line_nos"], [1, 3])
        self.assertEqual(payload["contract_no"], "HT1、HT4")

    def test_repeated_cancel_is_idempotent_and_does_not_duplicate_events(self):
        self.mark_contract_cancelled("HT1")
        self.insert_order_line("DO3", 1, "contracted", "HT1")

        first = self.cancel(["HT1"], operator="ops")
        second = self.cancel(["HT1"], operator="ops")

        self.assertEqual(first["lines"], 1)
        self.assertEqual(second["lines"], 0)
        self.assertEqual(second["orders"], [])
        self.assertEqual(len(self.outbox_events()), 1)

    def test_contract_not_cancelled_is_not_touched(self):
        self.insert_factory_plan("HT9", "已规划")
        self.insert_order_line("DO4", 1, "contracted", "HT9")

        result = self.cancel(["HT1"])

        self.assertEqual(result["lines"], 0)
        self.assertEqual(
            self.sql("SELECT status, contract_no FROM dealer_orders WHERE order_no='DO4'"),
            [("contracted", "HT9")],
        )
        self.assertEqual(self.outbox_events(), [])

    def test_contract_ids_accept_separators_and_list(self):
        self.mark_contract_cancelled("HT1", "HT5", "HT6", "HT7")
        self.insert_order_line("DO5", 1, "contracted", "HT1，HT5")
        self.insert_order_line("DO6", 1, "contracted", "HT6/HT7")

        result = self.cancel(["HT5", "HT7"])

        self.assertEqual(sorted(result["orders"]), ["DO5", "DO6"])
        self.assertEqual(
            self.sql("SELECT order_no, status FROM dealer_orders ORDER BY order_no"),
            [("DO5", "cancelled"), ("DO6", "cancelled")],
        )

    def test_multi_contract_line_requires_every_contract_cancelled(self):
        self.mark_contract_cancelled("HT1")
        self.insert_factory_plan("HT3", "已规划")
        self.insert_order_line("DO-A", 1, "contracted", "HT1、HT3")

        # 只取消 HT1：该行还引用未取消的 HT3 → 不动（保守语义，避免误伤）。
        result = self.cancel(["HT1"])
        self.assertEqual(result["lines"], 0)
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-A'"), [("contracted",)]
        )
        self.assertEqual(self.outbox_events(), [])

        # 合同在 factory_plan 查不到同样不动。
        self.insert_order_line("DO-B", 1, "contracted", "HT1、HT404")
        self.assertEqual(self.cancel(["HT1"])["lines"], 0)
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-B'"), [("contracted",)]
        )

        # HT3 也取消后才联动取消整行（单行订单不带 line_nos）。
        self.sql("UPDATE factory_plan SET `状态`='已取消' WHERE `合同号`='HT3'")
        result = self.cancel(["HT1"])
        self.assertEqual(result["orders"], ["DO-A"])
        self.assertEqual(
            self.sql("SELECT order_no, status FROM dealer_orders ORDER BY order_no"),
            [("DO-A", "cancelled"), ("DO-B", "contracted")],
        )
        events = self.outbox_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1], "DO-A")
        self.assertEqual(events[0][2]["contract_no"], "HT1、HT3")
        self.assertNotIn("line_nos", events[0][2])

    def test_line_ids_restricts_cancel_to_selected_rows(self):
        self.mark_contract_cancelled("HT1")
        self.insert_order_line("DO7", 1, "contracted", "HT1")
        self.insert_order_line("DO7", 2, "contracted", "HT1")
        line_id = self.scalar("SELECT id FROM dealer_orders WHERE order_no='DO7' AND line_no=2")

        result = self.cancel(["HT1"], line_ids=[line_id])

        self.assertEqual(result["lines"], 1)
        self.assertEqual(
            self.sql("SELECT line_no, status FROM dealer_orders WHERE order_no='DO7' ORDER BY line_no"),
            [(1, "contracted"), (2, "cancelled")],
        )
        _, _, payload = self.outbox_events()[0]
        self.assertEqual(payload["line_nos"], [2])

    def test_supersede_pending_events_called_before_enqueue(self):
        self.mark_contract_cancelled("HT1")
        self.insert_order_line("DO-S", 1, "contracted", "HT1")
        calls = []

        def record_supersede(conn, order_no, *, reason=""):
            calls.append(("supersede", order_no, reason))
            return 0

        def record_insert(conn, event_id, event_type, biz_key, payload_json):
            calls.append(("insert", event_type, biz_key))
            fake_insert_cloud_sync_event(conn, event_id, event_type, biz_key, payload_json)

        with patch(
            "crud.cloud_sync_outbox.supersede_pending_order_sync_events",
            side_effect=record_supersede,
            create=True,
        ), patch.object(dealer_orders, "insert_cloud_sync_event", side_effect=record_insert):
            self.cancel(["HT1"], reason="合同取消")

        # 先作废旧事件、再入队本次 cancel 事件，避免把刚入队的事件作废。
        self.assertEqual(
            calls,
            [
                ("supersede", "DO-S", "合同取消"),
                ("insert", "dealer_order_cancelled", "DO-S"),
            ],
        )
        self.assertEqual(len(self.outbox_events()), 1)

    def test_supersede_marks_old_pending_events_when_sync_layer_provides_it(self):
        if not hasattr(cloud_sync_outbox, "supersede_pending_order_sync_events"):
            self.skipTest("task-5 的 supersede_pending_order_sync_events 尚未落地")
        self.mark_contract_cancelled("HT1")
        self.insert_order_line("DO-OLD", 1, "contracted", "HT1")
        self.insert_outbox_event("dealer_order_allocated", "DO-OLD")

        self.cancel(["HT1"], reason="合同取消")

        rows = self.sql("SELECT event_type, status FROM cloud_sync_outbox ORDER BY id")
        self.assertEqual(rows[0], ("dealer_order_allocated", "superseded"))
        self.assertEqual(rows[1], ("dealer_order_cancelled", "pending"))


class SyncAllocationStatusWritebackTests(SqliteCase):
    def setUp(self):
        super().setUp()
        self.patch_insert = patch.object(
            dealer_orders, "insert_cloud_sync_event", side_effect=fake_insert_cloud_sync_event
        )
        self.patch_insert.start()
        self.addCleanup(self.patch_insert.stop)
        self.sql("CREATE TABLE sales_orders (`订单号` TEXT PRIMARY KEY, status TEXT)")
        self.sql(
            "CREATE TABLE finished_goods_data "
            "(`流水号` TEXT PRIMARY KEY, `占用订单号` TEXT, `机型` TEXT, `状态` TEXT)"
        )

    def sync(self, order_no):
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id"),
                {"order_no": order_no},
            ).fetchall()
            items = [dealer_orders._row_to_dict(row) for row in rows]
            return dealer_orders._sync_allocation_status(conn, order_no, items)

    def test_partial_allocated_is_not_writeback_as_allocated(self):
        self.insert_order_line("DO8", 1, "contracted", "C1", model="M1", quantity=3)
        self.insert_factory_plan("C1", "已规划", model="M1", order_id="V7-1")
        self.sql("INSERT INTO sales_orders VALUES ('V7-1', 'ready')")
        self.sql(
            "INSERT INTO finished_goods_data VALUES ('S1','V7-1','M1','待发货'),"
            "('S2','V7-1','M1','待发货')"
        )

        self.sync("DO8")

        self.assertEqual(
            self.sql("SELECT allocated_qty, status FROM dealer_orders WHERE order_no='DO8'"),
            [(2, "partial_allocated")],
        )
        event_type, biz_key, payload = self.outbox_events()[0]
        self.assertEqual(event_type, "dealer_order_allocated")
        self.assertEqual(biz_key, "DO8")
        self.assertEqual(payload["status"], "partial_allocated")

    def test_completed_lines_enqueue_completed_event(self):
        self.insert_order_line("DO9", 1, "contracted", "C2", model="M2", quantity=2)
        self.insert_factory_plan("C2", "已规划", model="M2", order_id="V7-2")
        self.sql("INSERT INTO sales_orders VALUES ('V7-2', 'done')")
        self.sql(
            "INSERT INTO finished_goods_data VALUES ('S3','V7-2','M2','待发货'),"
            "('S4','V7-2','M2','已出库')"
        )

        self.sync("DO9")

        self.assertEqual(
            self.sql("SELECT allocated_qty, status FROM dealer_orders WHERE order_no='DO9'"),
            [(2, "completed")],
        )
        event_type, biz_key, payload = self.outbox_events()[0]
        self.assertEqual(event_type, "dealer_order_completed")
        self.assertEqual(biz_key, "DO9")
        self.assertEqual(payload["order_no"], "DO9")


class ExtraReviewWritebackTests(SqliteCase):
    def setUp(self):
        super().setUp()
        self.patch_insert = patch.object(
            dealer_orders, "insert_cloud_sync_event", side_effect=fake_insert_cloud_sync_event
        )
        self.patch_insert.start()
        self.addCleanup(self.patch_insert.stop)

    def test_extra_review_keeps_contracted_status(self):
        self.insert_order_line("DO10", 1, "contracted", "HT1", factory_pending=1)
        with patch.object(dealer_orders, "ensure_dealer_order_tables"), patch.object(
            dealer_orders, "get_engine", return_value=self.engine
        ), patch.object(dealer_orders, "preview_dealer_order", return_value={"order": {}}):
            dealer_orders.approve_dealer_order_extra_review("DO10", "tester", "备注已确认")

        self.assertEqual(
            self.sql("SELECT status, factory_pending FROM dealer_orders WHERE order_no='DO10'"),
            [("contracted", 0)],
        )
        event_type, biz_key, payload = self.outbox_events()[0]
        self.assertEqual(event_type, "dealer_order_reviewed")
        self.assertEqual(biz_key, "DO10")
        self.assertEqual(payload["status"], "contracted")
        self.assertEqual(payload["factory_pending"], 0)

    def test_extra_review_falls_back_to_approved_for_unwritable_status(self):
        # regional_pending 不是云端可写状态：必须回退 approved，避免 outbox 永久 failed。
        self.insert_order_line("DO11", 1, "regional_pending", "HT1", factory_pending=1)
        with patch.object(dealer_orders, "ensure_dealer_order_tables"), patch.object(
            dealer_orders, "get_engine", return_value=self.engine
        ), patch.object(dealer_orders, "preview_dealer_order", return_value={"order": {}}):
            dealer_orders.approve_dealer_order_extra_review("DO11", "tester", "备注已确认")

        event_type, biz_key, payload = self.outbox_events()[0]
        self.assertEqual(event_type, "dealer_order_reviewed")
        self.assertEqual(biz_key, "DO11")
        self.assertEqual(payload["status"], "approved")


class PlanningCancelEntryTests(SqliteCase):
    def setUp(self):
        super().setUp()
        self.patches = [
            patch.object(planning, "get_engine", return_value=self.engine),
            patch.object(planning, "_trigger_sandbox_recompute_sync", return_value=True),
            patch.object(planning, "append_audit_log"),
            patch.object(planning, "_clear_planning_related_caches"),
            patch.object(planning, "_assert_internal_token"),
            patch.object(planning, "_ensure_cloud_sync_outbox_ready"),
            patch.object(
                dealer_orders, "insert_cloud_sync_event", side_effect=fake_insert_cloud_sync_event
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_contract_status_cancel_links_dealer_orders(self):
        self.insert_factory_plan("HT1", "已规划")
        self.insert_order_line("DO-HT1", 1, "contracted", "HT1")

        response = planning.update_contract_status(
            "HT1",
            planning.StatusPayload(status="已取消"),
            None,
            current_operator="tester",
            current_user={"username": "tester"},
        )

        self.assertEqual(
            self.sql("SELECT `状态` FROM factory_plan WHERE `合同号`='HT1'"), [("已取消",)]
        )
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-HT1'"), [("cancelled",)]
        )
        self.assertEqual(response["sync"]["dealer_orders"]["orders"], ["DO-HT1"])
        self.assertEqual(response["sync"]["dealer_orders"]["lines"], 1)
        self.assertIn("合同状态已更新为 已取消", response["message"])
        # outbox 表在业务事务外预建
        planning._ensure_cloud_sync_outbox_ready.assert_called_once()
        event_type, biz_key, payload = self.outbox_events()[0]
        self.assertEqual(event_type, "dealer_order_cancelled")
        self.assertEqual(biz_key, "DO-HT1")
        self.assertEqual(payload["note"], "合同 HT1 已取消")
        self.assertEqual(payload["operator"], "tester")

    def test_internal_contract_cancel_sync_links_dealer_orders(self):
        self.insert_factory_plan("HT2", "已规划")
        self.insert_order_line("DO-HT2", 1, "contracted", "HT2")

        response = planning.internal_contract_cancel_sync_api(
            planning.ContractCancelSyncPayload(contract_no="HT2", operator="go-op", source="go"),
            None,
        )

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["dealer_orders"]["orders"], ["DO-HT2"])
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-HT2'"), [("cancelled",)]
        )
        planning._ensure_cloud_sync_outbox_ready.assert_called_once()
        _, _, payload = self.outbox_events()[0]
        self.assertEqual(payload["operator"], "go-op")
        self.assertIn("go", payload["note"])

    def test_non_cancel_status_does_not_touch_dealer_orders(self):
        self.insert_factory_plan("HT3", "已规划")
        self.insert_order_line("DO-HT3", 1, "contracted", "HT3")

        response = planning.update_contract_status(
            "HT3",
            planning.StatusPayload(status="待规划"),
            None,
            current_operator="tester",
            current_user={"username": "tester"},
        )

        self.assertEqual(response["sync"]["dealer_orders"], {})
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-HT3'"), [("contracted",)]
        )
        self.assertEqual(self.outbox_events(), [])
        planning._ensure_cloud_sync_outbox_ready.assert_not_called()

    def test_already_cancelled_contract_replays_order_sync_instead_of_404(self):
        # 合同已经是已取消（cleanup rowcount=0）时，不再 404，而是幂等联动并补同步回传。
        self.insert_factory_plan("HT-ALREADY", "已取消")
        self.insert_order_line("DO-ALREADY", 1, "contracted", "HT-ALREADY")

        with patch.object(
            planning,
            "_cleanup_cancelled_contract_links",
            return_value={
                "factory_plan": 0,
                "production_queue": 0,
                "rush_order_queue": 0,
                "units": 0,
                "production_history_ledger": 0,
            },
        ):
            response = planning.update_contract_status(
                "HT-ALREADY",
                planning.StatusPayload(status="已取消"),
                None,
                current_operator="tester",
                current_user={"username": "tester"},
            )

        self.assertIn("合同已是已取消状态，已补同步订单回传", response["message"])
        self.assertEqual(response["sync"]["dealer_orders"]["orders"], ["DO-ALREADY"])
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-ALREADY'"),
            [("cancelled",)],
        )
        self.assertEqual(len(self.outbox_events()), 1)

        # 再次点击取消（订单已取消）→ 幂等，不再重复入队，并提示无需变更。
        with patch.object(
            planning,
            "_cleanup_cancelled_contract_links",
            return_value={"factory_plan": 0},
        ):
            second = planning.update_contract_status(
                "HT-ALREADY",
                planning.StatusPayload(status="已取消"),
                None,
                current_operator="tester",
                current_user={"username": "tester"},
            )
        self.assertIn("关联订单无需变更", second["message"])
        self.assertEqual(len(self.outbox_events()), 1)

    def test_missing_contract_still_returns_404(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as caught:
            planning.update_contract_status(
                "HT-NOT-EXIST",
                planning.StatusPayload(status="已取消"),
                None,
                current_operator="tester",
                current_user={"username": "tester"},
            )

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.outbox_events(), [])


class RepairScriptTests(SqliteCase):
    def setUp(self):
        super().setUp()
        self.patch_engine = patch.object(repair_script, "get_engine", return_value=self.engine)
        self.patch_ensure = patch("crud.cloud_sync_outbox.ensure_cloud_sync_outbox_table")
        self.patch_insert = patch.object(
            dealer_orders, "insert_cloud_sync_event", side_effect=fake_insert_cloud_sync_event
        )
        for item in (self.patch_engine, self.patch_ensure, self.patch_insert):
            item.start()
            self.addCleanup(item.stop)

    def prepare_rows(self):
        # 整单两个合同行都指向已取消合同 → 整单取消
        self.insert_factory_plan("HT1", "已取消", model="M1")
        self.insert_factory_plan("HT1", "已取消", model="M2")
        self.insert_order_line("DO-FULL", 1, "contracted", "HT1")
        self.insert_order_line("DO-FULL", 2, "contracted", "HT1")
        # 一行指向已取消合同，另一行指向待规划合同 → 只取消第一行
        self.insert_factory_plan("HT2", "待规划", model="M1")
        self.insert_order_line("DO-MIXED", 1, "contracted", "HT1")
        self.insert_order_line("DO-MIXED", 2, "contracted", "HT2")
        # 同一行引用已取消 + 未取消合同 → 跳过（必须每个合同都已取消）
        self.insert_order_line("DO-AND", 1, "contracted", "HT1、HT2")
        # 合同在 factory_plan 查不到 → 跳过
        self.insert_order_line("DO-MISSING", 1, "contracted", "HT404")

    def test_dry_run_reports_targets_and_skips_without_writing(self):
        self.prepare_rows()
        output = StringIO()
        with redirect_stdout(output):
            exit_code = repair_script.main([])

        self.assertEqual(exit_code, 0)
        text_output = output.getvalue()
        self.assertIn("dry-run", text_output)
        self.assertIn("order=DO-FULL", text_output)
        self.assertIn("order=DO-MIXED", text_output)
        self.assertIn("missing=['HT404']", text_output)
        self.assertIn("not_cancelled=['HT2']", text_output)
        self.assertEqual(
            self.sql("SELECT COUNT(*) FROM dealer_orders WHERE status='cancelled'"), [(0,)]
        )
        self.assertEqual(self.outbox_events(), [])

    def test_apply_cancels_targets_and_is_idempotent(self):
        self.prepare_rows()

        with redirect_stdout(StringIO()):
            exit_code = repair_script.main(["--apply", "--operator", "repairer"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            self.sql("SELECT order_no, line_no, status FROM dealer_orders ORDER BY order_no, line_no"),
            [
                ("DO-AND", 1, "contracted"),
                ("DO-FULL", 1, "cancelled"),
                ("DO-FULL", 2, "cancelled"),
                ("DO-MISSING", 1, "contracted"),
                ("DO-MIXED", 1, "cancelled"),
                ("DO-MIXED", 2, "contracted"),
            ],
        )
        events = {biz_key: payload for _, biz_key, payload in self.outbox_events()}
        self.assertEqual(sorted(events), ["DO-FULL", "DO-MIXED"])
        self.assertNotIn("line_nos", events["DO-FULL"])
        self.assertEqual(events["DO-MIXED"]["line_nos"], [1])
        self.assertIn("历史数据修复", events["DO-FULL"]["note"])

        first_event_count = len(self.outbox_events())
        with redirect_stdout(StringIO()):
            repair_script.main(["--apply"])
        self.assertEqual(len(self.outbox_events()), first_event_count)

    def test_order_no_filter_only_touches_selected_order(self):
        self.prepare_rows()

        with redirect_stdout(StringIO()):
            repair_script.main(["--apply", "--order-no", "DO-FULL"])

        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-FULL' AND line_no=1"),
            [("cancelled",)],
        )
        self.assertEqual(
            self.sql("SELECT status FROM dealer_orders WHERE order_no='DO-MIXED' AND line_no=1"),
            [("contracted",)],
        )
        self.assertEqual([biz_key for _, biz_key, _ in self.outbox_events()], ["DO-FULL"])


if __name__ == "__main__":
    unittest.main()
