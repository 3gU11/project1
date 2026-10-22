import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from fastapi import HTTPException
from api.routes import inventory as api


class CustomerOrderActionTests(unittest.TestCase):
    def preview(self, status="active", action="mark_shipped", sufficient=True):
        selected = [{"流水号": "s1", "占用订单号": "o1", "客户": "东莞客户"},
                    {"流水号": "s2", "占用订单号": "o1", "客户": "东莞客户"}]
        orders = [{"订单号": "o1", "客户名": "东莞客户", "status": status}]
        stock = [{"流水号": "s1", "占用订单号": "o1", "状态": "待发货"},
                 {"流水号": "s2", "占用订单号": "o1", "状态": "库存中（DG-WH）"}]
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(**{"mappings.return_value.all.return_value": rows}) for rows in [selected, orders, stock]]
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = conn
        with patch.object(api, "get_engine", return_value=engine), \
             patch("api.routes.planning.get_order_progress", return_value={"o1": {"order_status_label": "已完成" if status == "done" else ("待发货" if status == "ready" else "待配齐")}}), \
             patch("api.routes.planning._get_explicit_order_allocations", return_value=pd.DataFrame([{"流水号": "s1", "机型": "A"}])), \
             patch("api.routes.planning._inventory_rows_satisfy_order", return_value=sufficient):
            return api._customer_order_action_preview(api.CustomerOrderActionPayload(serial_nos=["s1", "s2"], action=action))

    def test_deduplicates_order_and_blocks_short_allocation(self):
        self.assertEqual(len(self.preview(status="ready")), 1)
        self.assertTrue(self.preview(status="ready")[0]["can_execute"])

    def test_shipping_only_pending_never_dg_inventory(self):
        row = self.preview(status="ready", action="mark_shipped")[0]
        self.assertTrue(row["can_execute"])
        self.assertEqual(row["serial_nos"], ["s1"])
        self.assertFalse(self.preview(action="mark_shipped")[0]["can_execute"])

    def test_shipping_blocks_allocated_order_that_is_not_fully_allocated(self):
        row = self.preview(status="allocated")[0]
        self.assertFalse(row["can_execute"])

    def test_terminal_orders_blocked(self):
        for status in ["done", "deleted", "canceled", "pending_review"]:
            self.assertFalse(self.preview(status=status)[0]["can_execute"])

    def test_execute_rejects_stale_preview_before_shipping(self):
        payload = api.CustomerOrderActionPayload(serial_nos=["s1"], action="mark_shipped", expected={"o1": "old"})
        with patch.object(api, "require_permissions", return_value=lambda user: user), \
             patch.object(api, "_customer_order_action_preview", return_value=[{"order_no": "o1", "fingerprint": "new", "can_execute": True}]), \
             patch.object(api, "confirm_shipping") as ship:
            with self.assertRaises(HTTPException) as caught:
                api.execute_customer_order_actions(payload, request=None, current_user={"username": "test"})
            self.assertEqual(caught.exception.status_code, 409)
            ship.assert_not_called()

    def test_permission_denied_before_read_or_write(self):
        payload = api.CustomerOrderActionPayload(serial_nos=["s1"], action="mark_shipped")
        with patch.object(api, "require_permissions", return_value=MagicMock(side_effect=HTTPException(403, "denied"))) as guard, \
             patch.object(api, "_customer_order_action_preview") as preview:
            with self.assertRaises(HTTPException):
                api.execute_customer_order_actions(payload, None, {})
            guard.assert_called_once_with("SHIP_CONFIRM")
            preview.assert_not_called()

    def test_shipping_transaction_rejects_replay_or_reassigned_machine(self):
        for row in [{"流水号": "s1", "占用订单号": "o1", "状态": "库存中（DG-WH）"},
                    {"流水号": "s1", "占用订单号": "another-order", "状态": "待发货"}]:
            conn = MagicMock()
            conn.execute.return_value.mappings.return_value.all.return_value = [row]
            engine = MagicMock()
            engine.begin.return_value.__enter__.return_value = conn
            with patch.object(api, "get_engine", return_value=engine):
                with self.assertRaises(HTTPException) as caught:
                    api.confirm_shipping(api.ShippingActionPayload(serial_nos=["s1"], expected_order_no="o1"), None, "tester", {"username": "tester"})
                self.assertEqual(caught.exception.status_code, 409)
                self.assertFalse(any("UPDATE finished_goods_data" in str(call.args[0]) for call in conn.execute.call_args_list))

    def test_actions_submit_model_without_direct_stock_change(self):
        for action, key in [("mark_shipped", "customer-order-shipped"), ("mark_in_stock", "customer-finished-recall")]:
            payload = api.CustomerOrderActionPayload(serial_nos=["s1"], action=action, expected={"o1": "ok"}, remark="测试备注")
            preview = [{"order_no": "o1", "fingerprint": "ok", "can_execute": True, "serial_nos": ["s1"]}]
            with patch.object(api, "require_permissions", return_value=lambda user: user), \
                 patch.object(api, "_customer_order_action_preview", return_value=preview), \
                 patch("api.routes.workflows.submit_reverse_instance", return_value={"data": {"instance_no": "WF-test", "status": "审批中"}}) as submit, \
                 patch.object(api, "confirm_shipping") as ship, \
                 patch.object(api, "get_engine") as database, \
                 patch.object(api, "append_audit_log") as audit:
                result = api.execute_customer_order_actions(payload, None, {"username": "test"})
                self.assertTrue(result["data"][0]["success"])
                self.assertIn("审批中", result["data"][0]["message"])
                self.assertEqual(submit.call_args.args[0].workflow_key, key)
                self.assertEqual(submit.call_args.args[0].items[0].object_id, "s1")
                ship.assert_not_called()
                database.assert_not_called()
                self.assertIn("测试备注", audit.call_args.kwargs["content"])


if __name__ == "__main__":
    unittest.main()
