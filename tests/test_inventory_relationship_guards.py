import unittest
from unittest.mock import MagicMock, patch

from crud.inventory_guards import require_inventory_order, validate_shipping_rows
from crud.inventory import inbound_to_slot, inbound_to_slot_v2
from crud.orders import allocate_inventory


class InventoryRelationshipGuardsTests(unittest.TestCase):
    def conn_for(self, row):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = row
        return conn

    def test_missing_and_cancelled_orders_are_rejected(self):
        for row in (None, {"status": "deleted"}, {"status": "cancelled"}, {"status": "canceled"}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                require_inventory_order(self.conn_for(row), "SO-1")
        conn = self.conn_for({"status": "active"})
        with self.assertRaises(ValueError):
            require_inventory_order(conn, " ")
        conn.execute.assert_not_called()

    def test_valid_orders_are_locked_and_accepted(self):
        for status in ("active", "ready"):
            conn = self.conn_for({"订单号": "SO-1", "status": status})
            self.assertEqual(require_inventory_order(conn, " SO-1 ")["status"], status)
            self.assertIn("FOR UPDATE", str(conn.execute.call_args.args[0]))
            self.assertEqual(conn.execute.call_args.args[1], {"order_id": "SO-1"})

    def test_shipping_rejects_stock_and_missing_machine(self):
        conn = self.conn_for({"status": "ready"})
        for status in ("库存中（H08）", "待入库", "报废"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                validate_shipping_rows(conn, [{"流水号": "SN", "状态": status}], ["SN"])
        with self.assertRaises(ValueError):
            validate_shipping_rows(conn, [], ["missing"])
        conn.execute.assert_not_called()

    def test_shipping_requires_order_and_preserves_idempotency(self):
        row = {"流水号": "SN", "状态": "待发货", "占用订单号": ""}
        with self.assertRaises(ValueError):
            validate_shipping_rows(self.conn_for(None), [row], ["SN"])
        row["占用订单号"] = "SO-1"
        validate_shipping_rows(self.conn_for({"status": "ready"}), [row], ["SN"])
        row["状态"] = "已出库"
        conn = self.conn_for(None)
        validate_shipping_rows(conn, [row], ["SN"])
        conn.execute.assert_not_called()

    @patch("crud.orders.get_engine")
    def test_empty_order_allocation_never_touches_database(self, engine):
        with self.assertRaises(ValueError):
            allocate_inventory("", "", "", ["SN"])
        engine.assert_not_called()

    @patch("crud.orders._build_model_note_map", return_value=[])
    @patch("crud.orders.get_engine")
    def test_deleted_order_allocation_stops_before_any_write(self, engine, notes):
        conn = self.conn_for({"status": "deleted"})
        engine.return_value.begin.return_value.__enter__.return_value = conn
        with self.assertRaises(RuntimeError):
            allocate_inventory("SO-1", "", "", ["SN"])
        self.assertEqual(conn.execute.call_count, 1)

    def test_both_inbound_paths_rollback_on_dangling_order(self):
        for fn in (inbound_to_slot, inbound_to_slot_v2):
            with self.subTest(fn=fn.__name__):
                conn = self.conn_for(None)
                conn.execute.return_value.fetchone.return_value = ("SN", "待发货", "missing")
                with patch("crud.inventory.get_engine") as engine, \
                     patch("crud.inventory.get_warehouse_layout", return_value={"layout_json": {"slots": [{"code": "老厂一车间400", "status": ""}]}}), \
                     patch("crud.inventory.pd.read_sql") as read_sql:
                    import pandas as pd
                    read_sql.return_value = pd.DataFrame(columns=["流水号", "Location_Code", "状态", "更新时间"])
                    engine.return_value.connect.return_value = conn
                    result = fn("SN", "老厂一车间400")
                self.assertFalse(result["ok"])
                conn.begin.return_value.rollback.assert_called_once()
                conn.begin.return_value.commit.assert_not_called()
                self.assertFalse(any(str(c.args[0]).lstrip().startswith("UPDATE") for c in conn.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
