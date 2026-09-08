import unittest
from unittest.mock import MagicMock, patch

from crud.orders import revert_to_inbound


class OrderInventoryReleaseTests(unittest.TestCase):
    @patch("crud.orders.append_log")
    @patch("crud.orders.enqueue_wechat_batch_summary_sync")
    @patch("crud.orders.clear_inventory_data_caches")
    @patch("crud.orders.get_engine")
    def test_release_updates_only_selected_rows(
        self,
        get_engine,
        clear_caches,
        enqueue_sync,
        append_log,
    ):
        conn = MagicMock()
        get_engine.return_value.begin.return_value.__enter__.return_value = conn

        revert_to_inbound(
            [" 96-06-207 ", "96-06-207", "96-06-208"],
            reason="订单配货释放-TEST",
            operator="tester",
        )

        self.assertEqual(conn.execute.call_count, 2)
        statements = [str(call.args[0]) for call in conn.execute.call_args_list]
        self.assertTrue(any("UPDATE finished_goods_data" in sql for sql in statements))
        self.assertTrue(any("UPDATE units" in sql for sql in statements))
        self.assertFalse(any("DELETE FROM finished_goods_data" in sql for sql in statements))
        for call in conn.execute.call_args_list:
            self.assertEqual(call.args[1]["sns"], ["96-06-207", "96-06-208"])
        clear_caches.assert_called_once_with()
        enqueue_sync.assert_called_once_with("orders_revert_to_inbound")
        append_log.assert_called_once_with(
            "订单配货释放-TEST-退回待入库",
            ["96-06-207", "96-06-208"],
            operator="tester",
        )

    @patch("crud.orders.get_engine")
    def test_release_with_no_serials_is_noop(self, get_engine):
        revert_to_inbound(["", "  "])
        get_engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
