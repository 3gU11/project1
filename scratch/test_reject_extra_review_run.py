import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import unittest
from unittest.mock import MagicMock, patch

# We mock database functions before importing dealer_orders if they run queries on load,
# but it's safe to import here as dealer_orders only defines functions.
from crud.dealer_orders import reject_dealer_order_extra_review

class TestRejectDealerOrderExtraReview(unittest.TestCase):
    @patch("crud.dealer_orders.get_engine")
    @patch("crud.dealer_orders.ensure_dealer_order_tables")
    @patch("crud.dealer_orders.preview_dealer_order")
    def test_reject_extra_review_success(self, mock_preview, mock_ensure_tables, mock_get_engine):
        # 1. Setup mock engine & connection
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        
        mock_conn = MagicMock()
        # Setup context manager begin()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        
        # 2. Setup mock query results
        # Query 1: _get_order_lines_for_update
        # Returns order lines. We need factory_pending=1 and some factory_remark or extra_remark.
        mock_row1 = MagicMock()
        mock_row1._mapping = {
            "id": 1,
            "order_no": "TEST_ORDER_001",
            "line_no": 1,
            "factory_pending": 1,
            "factory_remark": "Need special customization",
            "extra_remark": "",
            "contract_no": "CONTRACT_001",
            "v7_order_no": "SO_001",
        }
        
        # Query 2 (within _cancel_linked_contract_order_chain):
        # FP orders: SELECT DISTINCT `订单号` FROM factory_plan WHERE ...
        mock_fp_row = MagicMock()
        mock_fp_row.__getitem__.return_value = "SO_001"
        
        # Query 3: finished goods serials for sales order IDs
        # SELECT DISTINCT `流水号` FROM finished_goods_data WHERE ...
        mock_fg_row1 = MagicMock()
        mock_fg_row1.__getitem__.return_value = "SN_001"
        
        # Query 4: finished goods serials for contracts
        mock_fg_row2 = MagicMock()
        mock_fg_row2.__getitem__.return_value = "SN_002"
        
        # We need mock_conn.execute().fetchall() or .fetchall() to return list of these mock rows
        mock_result_get_lines = MagicMock()
        mock_result_get_lines.fetchall.return_value = [mock_row1]
        
        mock_result_fp = MagicMock()
        mock_result_fp.fetchall.return_value = [mock_fp_row]
        
        mock_result_fg1 = MagicMock()
        mock_result_fg1.fetchall.return_value = [mock_fg_row1]
        
        mock_result_fg2 = MagicMock()
        mock_result_fg2.fetchall.return_value = [mock_fg_row2]
        
        # Assign side effects to conn.execute
        # Let's count calls to return different values
        def execute_side_effect(statement, *args, **kwargs):
            stmt_str = str(statement).upper()
            print(f"Executing SQL mock: {stmt_str}")
            if "FROM DEALER_ORDERS" in stmt_str:
                return mock_result_get_lines
            elif "FROM FACTORY_PLAN" in stmt_str:
                return mock_result_fp
            elif "FROM FINISHED_GOODS_DATA" in stmt_str:
                # Two calls: one for sales_order_ids, one for contract_nos
                if "占用订单号" in stmt_str:
                    return mock_result_fg1
                else:
                    return mock_result_fg2
            # For UPDATE/INSERT statements, return a dummy result
            dummy_res = MagicMock()
            dummy_res.rowcount = 1
            return dummy_res

        mock_conn.execute.side_effect = execute_side_effect
        
        # Setup mock preview
        mock_preview.return_value = {"order_no": "TEST_ORDER_001", "status": "rejected"}
        
        # 3. Call target function
        result = reject_dealer_order_extra_review(
            order_no="TEST_ORDER_001",
            reviewer="admin",
            reason="reject reason"
        )
        
        # 4. Asserts
        print(f"Result: {result}")
        self.assertEqual(result["status"], "rejected")
        self.assertIn("cascade_cancel", result)
        self.assertEqual(result["cascade_cancel"]["cancelled_contracts"], ["CONTRACT_001"])
        self.assertEqual(result["cascade_cancel"]["cancelled_orders"], ["SO_001"])
        self.assertEqual(sorted(result["cascade_cancel"]["released_serials"]), ["SN_001", "SN_002"])
        print("Success! No NameError or any exception occurred during execution.")

if __name__ == "__main__":
    unittest.main()
