import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd

from sqlalchemy import create_engine, event, text

from crud.order_reservations import release_completed_order_reservations


class CompletedOrderReservationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, 'connect')
        def functions(conn, _):
            conn.create_function('NOW', 0, lambda: '2026-09-22')

        @event.listens_for(self.engine, 'before_cursor_execute', retval=True)
        def locks(conn, cursor, statement, params, context, many):
            return statement.replace('FOR UPDATE', ''), params

        with self.engine.begin() as c:
            for sql in [
                'CREATE TABLE sales_orders (`订单号` TEXT,status TEXT,`需求机型` TEXT,`需求数量` INTEGER)',
                'CREATE TABLE finished_goods_data (`流水号` TEXT,`占用订单号` TEXT,`状态` TEXT,`机型` TEXT)',
                'CREATE TABLE batches (batch_id TEXT,status TEXT)',
                'CREATE TABLE units (unit_id TEXT,batch_id TEXT,status TEXT,serial_no TEXT,forecast_serial_no TEXT,production_line_id TEXT,is_locked INTEGER,is_contract_pinned INTEGER,sales_id TEXT,contract_no TEXT,customer TEXT,dealer_id TEXT,dealer_name TEXT,due_date TEXT,order_remark TEXT,updated_at TEXT)',
                "INSERT INTO sales_orders VALUES ('O1','done','FR-8060AUTOx1',1)",
                "INSERT INTO finished_goods_data VALUES ('S1','O1','已出库','FR-8060AUTO')",
                "INSERT INTO batches VALUES ('B1','Predicted')",
                "INSERT INTO units (unit_id,batch_id,status,sales_id,contract_no) VALUES ('U1','B1','Pending','O1','C1')",
            ]:
                c.execute(text(sql))

    def sql(self, query):
        with self.engine.begin() as c:
            result=c.execute(text(query))
            return result.fetchall() if result.returns_rows else []

    def release(self):
        with self.engine.begin() as c:
            return release_completed_order_reservations(c, ['O1'])

    def test_complete_order_releases_anonymous_reservation_only(self):
        rows=self.release()
        self.assertEqual([r['unit_id'] for r in rows], ['U1'])
        self.assertEqual(self.sql('SELECT unit_id,batch_id,status,contract_no,sales_id FROM units'), [('U1','B1','Pending',None,None)])
        self.assertEqual(self.sql('SELECT * FROM finished_goods_data'), [('S1','O1','已出库','FR-8060AUTO')])
        self.assertEqual(self.release(), [])

    def test_incomplete_and_wrong_model_shipments_keep_reservation(self):
        for update in ["UPDATE sales_orders SET status='ready'", "UPDATE sales_orders SET status='done',`需求机型`='FR-600AUTOx1'", "UPDATE sales_orders SET `需求机型`='FR-8060AUTOx2'", "UPDATE sales_orders SET `需求机型`='FR-8060AUTOx1;FR-600AUTOx1'"]:
            self.sql(update)
            self.assertEqual(self.release(), [])

    def test_duplicate_inventory_rows_do_not_complete_demand(self):
        self.sql('INSERT INTO finished_goods_data SELECT * FROM finished_goods_data')
        self.sql("UPDATE sales_orders SET `需求机型`='FR-8060AUTOx2'")
        self.assertEqual(self.release(), [])

    def test_real_machine_locked_pinned_and_active_production_are_protected(self):
        for field,value in [('serial_no',"'S2'"),('forecast_serial_no',"'S2'"),('production_line_id',"'L1'"),('is_locked','1'),('is_contract_pinned','1'),('status',"'In_Production'")]:
            self.sql(f'UPDATE units SET {field}={value}')
            self.assertEqual(self.release(), [], field)
            self.sql(f"UPDATE units SET {field}=" + ("'Pending'" if field=='status' else 'NULL'))
        self.sql("UPDATE batches SET status='In_Production'")
        self.assertEqual(self.release(), [])

    def test_other_order_and_cancelled_order_are_untouched(self):
        self.sql("UPDATE units SET sales_id='OTHER'")
        self.assertEqual(self.release(), [])
        self.sql("UPDATE units SET sales_id='O1'")
        self.sql("UPDATE sales_orders SET status='deleted'")
        self.assertEqual(self.release(), [])

    def test_failure_rolls_back_changes(self):
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as c:
                release_completed_order_reservations(c,['O1'])
                raise RuntimeError('rollback')
        self.assertEqual(self.sql('SELECT contract_no,sales_id FROM units'), [('C1','O1')])

    def _confirm_shipping(self, cleanup_failure=False):
        from api.routes import inventory

        self.sql('ALTER TABLE finished_goods_data ADD COLUMN `更新时间` TEXT')
        self.sql("UPDATE sales_orders SET status='ready'")
        self.sql("UPDATE finished_goods_data SET `状态`='待发货'")

        def read_orders():
            with self.engine.connect() as c:
                return pd.read_sql(text('SELECT * FROM sales_orders'), c)

        def save_orders(frame):
            # Adapt MySQL bulk upsert to SQLite; retain the real shipping and
            # reservation queries and their separate transactions.
            with self.engine.begin() as c:
                for row in frame.to_dict('records'):
                    c.execute(text('UPDATE sales_orders SET status=:status WHERE `订单号`=:oid'),
                              {'status':row['status'],'oid':row['订单号']})

        with ExitStack() as stack:
            stack.enter_context(patch.object(inventory, 'get_engine', return_value=self.engine))
            stack.enter_context(patch.object(inventory, 'get_orders', side_effect=read_orders))
            stack.enter_context(patch.object(inventory, 'save_orders', side_effect=save_orders))
            for name in ['archive_shipped_data','append_log','append_audit_log',
                         'enqueue_wechat_batch_summary_sync','enqueue_cloud_sync_event']:
                stack.enter_context(patch.object(inventory,name))
            stack.enter_context(patch.object(inventory,'sync_dealer_order_statuses_by_sales_orders',return_value=[]))
            if cleanup_failure:
                stack.enter_context(patch.object(inventory,'release_completed_order_reservations',side_effect=RuntimeError('test cleanup failure')))
            return inventory.confirm_shipping(inventory.ShippingActionPayload(serial_nos=['S1']),
                                              request=None,current_operator='tester',current_user={'username':'tester'})

    def test_confirm_shipping_completes_order_and_releases_reservation(self):
        response=self._confirm_shipping()
        self.assertEqual(response['warning'],'')
        self.assertEqual(self.sql('SELECT status FROM sales_orders'), [('done',)])
        self.assertEqual(self.sql('SELECT `状态` FROM finished_goods_data'), [('已出库',)])
        self.assertEqual(self.sql('SELECT contract_no,sales_id FROM units'), [(None,None)])

    def test_partial_shipment_does_not_release_remaining_demand(self):
        self.sql("UPDATE sales_orders SET `需求机型`='FR-8060AUTOx2', `需求数量`=2")
        self._confirm_shipping()
        self.assertEqual(self.sql('SELECT status FROM sales_orders'), [('ready',)])
        self.assertEqual(self.sql('SELECT contract_no,sales_id FROM units'), [('C1','O1')])

    def test_cleanup_failure_preserves_successful_shipment_and_reports_warning(self):
        response=self._confirm_shipping(cleanup_failure=True)
        self.assertIn('沙盘预留清理失败', response['warning'])
        self.assertEqual(self.sql('SELECT status FROM sales_orders'), [('done',)])
        self.assertEqual(self.sql('SELECT `状态` FROM finished_goods_data'), [('已出库',)])
        self.assertEqual(self.sql('SELECT contract_no,sales_id FROM units'), [('C1','O1')])
