import inspect
import unittest

from api.routes.planning import (
    complete_order_allocation_api,
    _get_order_contract_machine_rows,
    _sync_order_detail_rows_to_units_and_inventory,
    _sync_order_to_units_and_import,
    _sync_units_from_contract_edit,
)
from crud.orders import allocate_inventory


class OrderAllocationGuardTests(unittest.TestCase):
    def test_queued_cards_are_not_allocatable(self):
        for fn in (_get_order_contract_machine_rows, allocate_inventory):
            source = inspect.getsource(fn)
            self.assertIn("b.status = 'In_Production' AND u.status = 'In_Production'", source)
            self.assertIn("p.line_id=u.production_line_id AND p.status='Busy'", source)
            self.assertIn("b.status IN ('Predicted', 'Confirmed')", source)
        self.assertIn('待排产机台不能配货', inspect.getsource(allocate_inventory))

    def test_order_creation_does_not_acquire_unrelated_production_units(self):
        source = inspect.getsource(_sync_order_detail_rows_to_units_and_inventory)
        self.assertNotIn("LIMIT :missing", source)
        self.assertNotIn("SET sales_id = :order_id", source)

    def test_contract_link_does_not_reserve_units_or_inventory(self):
        source = inspect.getsource(_sync_order_to_units_and_import)
        self.assertNotIn("UPDATE units SET sales_id", source)
        self.assertNotIn("UPDATE finished_goods_data SET", source)

    def test_contract_edit_does_not_reserve_contract_units(self):
        source = inspect.getsource(_sync_units_from_contract_edit)
        self.assertNotIn("sales_id = CASE WHEN :order_id", source)

    def test_physical_inventory_is_excluded_from_production_candidates(self):
        candidate_source = inspect.getsource(_get_order_contract_machine_rows)
        allocation_source = inspect.getsource(allocate_inventory)
        for source in (candidate_source, allocation_source):
            self.assertIn("NOT LIKE '库存中%'", source)
            self.assertIn("'待发货', '已出库', '已发货', '报废'", source)

    def test_manual_production_allocation_goes_directly_to_pending_shipment(self):
        source = inspect.getsource(allocate_inventory)
        self.assertIn("VALUES (:sn,:batch,:model,'待发货'", source)
        self.assertIn("`合同备注`=:note, `合同号`=:contract_no, `状态`='待发货'", source)
        self.assertNotIn("`状态`='待入库'", source)
        self.assertIn("if update_result.rowcount == 0:", source)
        self.assertNotIn("ON DUPLICATE KEY UPDATE", source)

    def test_complete_allocation_never_creates_waiting_inbound_order_state(self):
        source = inspect.getsource(complete_order_allocation_api)
        self.assertNotIn('next_status = "allocated"', source)
        self.assertIn('"status": "ready"', source)


if __name__ == "__main__":
    unittest.main()
