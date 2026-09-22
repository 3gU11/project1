"""Exercise real transactions on an isolated database; never use business data."""
import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text, event

from crud import batch_planning as bp


class BatchPlanningTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.patches = [patch.object(bp, "get_engine", return_value=self.engine), patch.object(bp, "_clear_caches")]
        for p in self.patches:
            p.start()
        schema = [
            "CREATE TABLE factory_plan (id INTEGER PRIMARY KEY, `合同号` TEXT, `机型` TEXT, `排产数量` TEXT, `备注` TEXT, `客户名` TEXT, `代理商` TEXT, `要求交期` TEXT, `状态` TEXT, `订单号` TEXT, `指定批次/来源` TEXT)",
            "CREATE TABLE sales_orders (`订单号` TEXT PRIMARY KEY,`客户名` TEXT,`代理商` TEXT,`需求机型` TEXT,`需求数量` INTEGER,`下单时间` TEXT,`备注` TEXT,`包装选项` TEXT,`指定批次/来源` TEXT,status TEXT)",
            "CREATE TABLE batches (batch_id TEXT PRIMARY KEY,batch_code TEXT,status TEXT,expected_inbound_date TEXT)",
            "CREATE TABLE units (unit_id TEXT PRIMARY KEY,batch_id TEXT,slot_index INTEGER,serial_no TEXT,forecast_serial_no TEXT,model_type TEXT,order_remark TEXT,contract_no TEXT,sales_id TEXT,customer TEXT,dealer_name TEXT,due_date TEXT,is_locked INTEGER DEFAULT 0,is_contract_pinned INTEGER DEFAULT 0,status TEXT,production_line_id TEXT,updated_at TEXT)",
            "CREATE TABLE finished_goods_data (`流水号` TEXT PRIMARY KEY,`机型` TEXT,`状态` TEXT,`合同号` TEXT,`占用订单号` TEXT,`客户` TEXT,`代理商` TEXT,`合同备注` TEXT,`批次号` TEXT,`预计入库时间` TEXT,`更新时间` TEXT)",
            "CREATE TABLE production_queue (contract_no TEXT,quantity_remaining INTEGER,status TEXT)",
            "CREATE TABLE rush_order_queue (contract_no TEXT,status TEXT,updated_by TEXT)",
            "CREATE TABLE production_lines (line_id TEXT,status TEXT)",
        ]
        with self.engine.begin() as c:
            for sql in schema:
                c.execute(text(sql))
            c.execute(text("INSERT INTO factory_plan VALUES (1,'C1','FR-500','2','','客户','代理','','待规划',NULL,NULL)"))
            c.execute(text("INSERT INTO batches VALUES ('B1','09-01','In_Production',NULL),('B2','09-02','Confirmed',NULL)"))
            c.execute(text("INSERT INTO production_lines VALUES ('L1','Busy')"))
            c.execute(text("INSERT INTO production_queue VALUES ('C1',2,'Waiting')"))
            c.execute(text("INSERT INTO rush_order_queue VALUES ('C1','pending','')"))
            for i in range(4):
                c.execute(text("""INSERT INTO units (unit_id,batch_id,slot_index,serial_no,model_type,status,production_line_id)
                    VALUES (:id,:bid,:n,:sn,'FR-500',:status,'L1')"""),
                    {"id":f"U{i}","bid":"B1" if i<2 else "B2","n":i,"sn":f"S{i}","status":"In_Production" if i<2 else "Pending"})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.engine.dispose()

    def sql(self, query, **params):
        with self.engine.begin() as c:
            result=c.execute(text(query),params)
            return result.fetchall() if result.returns_rows else []

    def test_matching_and_no_cross_batch_fill(self):
        self.assertEqual(len(bp.eligible_batches("C1")),2)
        self.sql("UPDATE units SET contract_no='OTHER' WHERE unit_id IN ('U0','U2')")
        self.assertEqual(bp.eligible_batches("C1"),[])
        with self.assertRaises(bp.BatchPlanningError):
            bp.plan_contract("C1","B1","planner")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM sales_orders")[0][0],0)

    def test_model_high_and_locked_cards(self):
        self.sql("UPDATE units SET order_remark='加高' WHERE unit_id='U0'")
        self.sql("UPDATE units SET is_locked=1 WHERE unit_id='U2'")
        self.assertEqual(bp.eligible_batches("C1"),[])

    def test_plan_is_atomic_and_idempotent(self):
        result=bp.plan_contract("C1","B1","planner")
        replay=bp.plan_contract("C1","B1","planner")
        self.assertEqual(result["order_id"],replay["order_id"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM sales_orders")[0][0],1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM finished_goods_data")[0][0],0)
        self.assertEqual(self.sql("SELECT `状态` FROM factory_plan")[0][0],"已转订单")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM units WHERE sales_id=:oid",oid=result["order_id"])[0][0],2)
        self.assertEqual(self.sql("SELECT quantity_remaining FROM production_queue")[0][0],0)
        self.assertEqual(len(bp.review_rows(result["order_id"])),2)

    def test_transaction_rolls_back_after_order_insert(self):
        def fail(conn,cursor,statement,parameters,context,executemany):
            if statement.startswith("UPDATE factory_plan"):
                raise RuntimeError("injected failure")
        event.listen(self.engine,"before_cursor_execute",fail)
        with self.assertRaises(RuntimeError):
            bp.plan_contract("C1","B1","planner")
        event.remove(self.engine,"before_cursor_execute",fail)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM sales_orders")[0][0],0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM units WHERE sales_id IS NOT NULL")[0][0],0)

    def test_stale_selection_is_rejected(self):
        bp.eligible_batches("C1")
        self.sql("UPDATE units SET sales_id='OTHER' WHERE unit_id='U0'")
        with self.assertRaises(bp.BatchPlanningError):
            bp.plan_contract("C1","B1","planner")
        self.assertEqual(self.sql("SELECT sales_id FROM units WHERE unit_id='U0'")[0][0],"OTHER")

    def test_confirm_production_allocation_and_retry(self):
        oid=bp.plan_contract("C1","B1","planner")["order_id"]
        self.assertEqual(bp.confirm_review(oid,"picker")["status"],"ready")
        self.assertTrue(bp.confirm_review(oid,"picker")["replayed"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM finished_goods_data WHERE `状态`='待发货'")[0][0],2)
        data=json.loads(self.sql("SELECT `指定批次/来源` FROM sales_orders")[0][0])
        self.assertEqual(data["_batch_plan"]["reviewed_by"],"picker")

    def test_queued_batch_waits_for_production(self):
        oid=bp.plan_contract("C1","B2","planner")["order_id"]
        with self.assertRaises(bp.BatchPlanningError):
            bp.confirm_review(oid,"picker")
        self.assertEqual(self.sql("SELECT status FROM sales_orders")[0][0],bp.REVIEW_STATUS)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM finished_goods_data")[0][0],0)

    def test_review_failure_rolls_back_earlier_machine(self):
        oid=bp.plan_contract("C1","B1","planner")["order_id"]
        self.sql("INSERT INTO finished_goods_data (`流水号`,`状态`) VALUES ('S1','报废')")
        with self.assertRaises(bp.BatchPlanningError):
            bp.confirm_review(oid,"picker")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM finished_goods_data WHERE `流水号`='S0'")[0][0],0)
        self.assertEqual(self.sql("SELECT status FROM sales_orders")[0][0],bp.REVIEW_STATUS)

    def test_changed_reservation_is_rejected(self):
        oid=bp.plan_contract("C1","B1","planner")["order_id"]
        self.sql("UPDATE units SET sales_id=NULL WHERE unit_id='U0'")
        with self.assertRaises(bp.BatchPlanningError):
            bp.confirm_review(oid,"picker")

    def test_inbound_reservation_found_without_inventory_mirror(self):
        oid=bp.plan_contract("C1","B1","planner")["order_id"]
        with self.engine.connect() as c:
            self.assertEqual(bp.pending_review_order(c,"S0"),oid)
            self.assertEqual(bp.pending_review_order(c,"S2"),"")

    def test_multiple_models_require_same_batch(self):
        self.sql("INSERT INTO factory_plan (id,`合同号`,`机型`,`排产数量`,`状态`) VALUES (2,'C1','FR-600','1','待规划')")
        self.assertEqual(bp.eligible_batches("C1"),[])
        self.sql("INSERT INTO units (unit_id,batch_id,slot_index,serial_no,model_type,status) VALUES ('UX','B1',3,'SX','FR-600','In_Production')")
        self.assertEqual([b["batch_id"] for b in bp.eligible_batches("C1")],["B1"])

    def test_predicted_and_completed_batches_not_offered(self):
        self.sql("UPDATE batches SET status='Predicted' WHERE batch_id='B1'")
        self.sql("UPDATE batches SET status='Completed' WHERE batch_id='B2'")
        self.assertEqual(bp.eligible_batches("C1"),[])

    def test_inbound_stock_can_be_confirmed_without_replacing_units(self):
        oid=bp.plan_contract("C1","B1","planner")["order_id"]
        self.sql("UPDATE batches SET status='Completed' WHERE batch_id='B1'")
        self.sql("UPDATE units SET status='Completed' WHERE batch_id='B1'")
        for sn in ('S0','S1'):
            self.sql("INSERT INTO finished_goods_data (`流水号`,`状态`,`占用订单号`) VALUES (:sn,'库存中（A1）',:oid)",sn=sn,oid=oid)
        self.assertEqual(bp.confirm_review(oid,"picker")["status"],"ready")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM finished_goods_data")[0][0],2)

    def test_http_permission_and_pending_review_guard(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes import planning, auth
        app=FastAPI()
        app.include_router(planning.router,prefix="/planning")
        app.dependency_overrides[auth.get_current_user_token]=lambda: "qa"
        app.dependency_overrides[auth.get_current_user_context]=lambda: {"username":"qa","role":"qa"}
        app.dependency_overrides[auth.get_current_operator_name]=lambda: "qa"
        with TestClient(app) as client, patch.object(auth,"get_role_permissions",return_value=[]):
            self.assertEqual(client.get('/planning/contract/C1/eligible-batches').status_code,403)
            self.assertEqual(client.post('/planning/contract/C1/plan-batch',json={"batch_id":"B1"}).status_code,403)
            self.assertEqual(client.post('/planning/orders/O1/confirm-batch-allocation').status_code,403)
        oid=bp.plan_contract("C1","B1","planner")["order_id"]
        # Route-level guard uses the same isolated connection on this thread.
        with patch.object(planning,"get_engine",return_value=self.engine):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as caught:
                planning._guard_pending_batch_review(oid)
            self.assertEqual(caught.exception.status_code,409)


if __name__ == "__main__":
    unittest.main()
