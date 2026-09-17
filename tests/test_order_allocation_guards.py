import inspect
import unittest

from api.routes.planning import (
    _get_order_contract_machine_rows,
    _sync_order_detail_rows_to_units_and_inventory,
    _sync_order_to_units_and_import,
    _sync_units_from_contract_edit,
)
from crud.orders import allocate_inventory


class OrderAllocationGuardTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
