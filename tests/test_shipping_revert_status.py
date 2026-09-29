"""Run the shipping endpoint against an isolated DB, never business records."""
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, text

from crud import orders
from api.routes import inventory


class ShippingRevertStatusTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')

        @event.listens_for(self.engine, 'connect')
        def functions(conn, _):
            conn.create_function('NOW', 0, lambda: '2026-09-22 14:00:00')
            conn.create_function('CONCAT', -1, lambda *args: ''.join(args))

        @event.listens_for(self.engine, 'before_cursor_execute', retval=True)
        def mysql_lock_syntax(conn, cursor, statement, parameters, context, executemany):
            return statement.replace('FOR UPDATE', ''), parameters

        self.patches = [
            patch.object(orders, 'get_engine', return_value=self.engine),
            patch.object(orders, 'clear_inventory_data_caches'),
            patch.object(orders, 'enqueue_wechat_batch_summary_sync'),
            patch.object(orders, 'append_log'),
            patch.object(inventory, 'append_audit_log'),
            patch.object(orders.get_orders, 'cache_clear'),
            patch.object(orders.get_orders_v2, 'cache_clear'),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            for sql in [
                'CREATE TABLE sales_orders (`订单号` TEXT PRIMARY KEY, status TEXT)',
                'CREATE TABLE finished_goods_data (`流水号` TEXT PRIMARY KEY, `占用订单号` TEXT, `状态` TEXT, `Location_Code` TEXT, `客户` TEXT, `代理商` TEXT, `合同号` TEXT, `更新时间` TEXT)',
                'CREATE TABLE batches (batch_id TEXT, status TEXT)',
                'CREATE TABLE units (serial_no TEXT, forecast_serial_no TEXT, batch_id TEXT, sales_id TEXT, contract_no TEXT, customer TEXT, dealer_name TEXT, due_date TEXT, is_locked INTEGER, locked_by TEXT, locked_at TEXT, updated_at TEXT)',
                "INSERT INTO sales_orders VALUES ('O1','ready'),('O2','ready'),('O3','deleted')",
                "INSERT INTO batches VALUES ('B1','In_Production')",
                "INSERT INTO finished_goods_data (`流水号`,`占用订单号`,`状态`,`Location_Code`) VALUES ('S1','O1','待发货','A01'),('S2','O1','待发货','A02'),('S3','O2','待发货',''),('S4','O3','待发货','')",
                "INSERT INTO units (serial_no, batch_id, sales_id,is_locked) VALUES ('S3','B1','O2',1)",
            ]:
                c.execute(text(sql))

    def rows(self, sql):
        with self.engine.connect() as c:
            return c.execute(text(sql)).fetchall()

    def revert(self, sns):
        return inventory.revert_shipping(
            inventory.ShippingActionPayload(serial_nos=sns), request=None,
            current_operator='tester', current_user={'username': 'tester'},
        )

    def test_endpoint_partial_withdrawal_reopens_order_and_keeps_other_allocations(self):
        self.revert(['S1'])
        self.assertEqual(self.rows('SELECT status FROM sales_orders ORDER BY `订单号`'),
                         [('active',), ('ready',), ('deleted',)])
        self.assertEqual(self.rows("SELECT `状态`,`占用订单号` FROM finished_goods_data WHERE `流水号`='S1'"),
                         [('库存中（A01）', None)])
        self.assertEqual(self.rows("SELECT `状态`,`占用订单号` FROM finished_goods_data WHERE `流水号`='S2'"),
                         [('待发货', 'O1')])
        orders.get_orders.cache_clear.assert_called_once()
        orders.get_orders_v2.cache_clear.assert_called_once()

    def test_multiple_orders_production_unbind_and_deleted_order_preserved(self):
        self.revert(['S1', 'S3', 'S4'])
        self.assertEqual(self.rows('SELECT status FROM sales_orders ORDER BY `订单号`'),
                         [('active',), ('active',), ('deleted',)])
        self.assertEqual(self.rows('SELECT sales_id,is_locked FROM units'), [(None, 0)])
        self.assertEqual(self.rows("SELECT `状态` FROM finished_goods_data WHERE `流水号`='S3'"), [('待入库',)])

    def test_unit_only_allocation_reopens_order(self):
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM finished_goods_data WHERE `流水号`='S3'"))
        self.revert(['S3'])
        self.assertEqual(self.rows("SELECT status FROM sales_orders WHERE `订单号`='O2'"), [('active',)])

    def test_failure_to_update_order_rolls_back_machine_changes(self):
        with self.engine.begin() as c:
            c.execute(text("CREATE TRIGGER reject_order_update BEFORE UPDATE ON sales_orders BEGIN SELECT RAISE(ABORT, 'test failure'); END"))
        with self.assertRaises(inventory.HTTPException) as caught:
            self.revert(['S3'])
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(self.rows("SELECT `状态`,`占用订单号` FROM finished_goods_data WHERE `流水号`='S3'"), [('待发货', 'O2')])
        self.assertEqual(self.rows('SELECT sales_id,is_locked FROM units'), [('O2', 1)])
        orders.get_orders.cache_clear.assert_not_called()

    def test_repeated_and_unknown_serials_do_not_change_other_orders(self):
        self.revert(['S1', 'S1', 'missing'])
        self.revert(['S1'])
        self.assertEqual(self.rows('SELECT status FROM sales_orders ORDER BY `订单号`'),
                         [('active',), ('ready',), ('deleted',)])


if __name__ == '__main__':
    unittest.main()
