import unittest

from crud.dealer_orders import (
    dealer_order_line_route,
    is_preorder_dealer_order_line,
)


class PreorderLineClassificationTests(unittest.TestCase):
    def test_unmarked_empty_batch_is_preorder(self):
        self.assertTrue(is_preorder_dealer_order_line("", "unmarked"))
        self.assertTrue(is_preorder_dealer_order_line(None, "UNMARKED"))
        self.assertEqual("preorder", dealer_order_line_route("", "unmarked"))

    def test_marked_preorder_alias_is_preorder(self):
        self.assertTrue(is_preorder_dealer_order_line("", "preorder"))
        self.assertTrue(is_preorder_dealer_order_line("", "无货预订"))

    def test_empty_batch_without_preorder_marker_stays_stock(self):
        # 10-23 修复：外部系统不下发批次的历史订单仍按现货校验
        self.assertFalse(is_preorder_dealer_order_line("", "finished"))
        self.assertFalse(is_preorder_dealer_order_line("", ""))
        self.assertEqual("spot", dealer_order_line_route("", "finished"))

    def test_specific_batch_is_not_preorder(self):
        self.assertFalse(is_preorder_dealer_order_line("10-02", "wip"))
        self.assertEqual("batch", dealer_order_line_route("10-02", "wip"))
        self.assertEqual("spot", dealer_order_line_route("FINISHED-STOCK", "finished"))
        self.assertEqual("spot", dealer_order_line_route("库存中", "finished"))


if __name__ == "__main__":
    unittest.main()
