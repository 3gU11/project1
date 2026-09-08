import unittest

from crud.inventory import (
    LARGE_WAREHOUSE_MAX_CAPACITY,
    OLD_FACTORY_SLOT_CODES,
    REQUIRED_SLOT_CODES,
    UNLIMITED_WAREHOUSE_CAPACITY,
    enrich_warehouse_layout,
    get_slot_capacity,
    merge_required_warehouse_slots,
)


def _slot(code: str, index: int = 0) -> dict:
    return {
        "id": f"slot-{index}",
        "code": code,
        "x": 20 + index * 10,
        "y": 20,
        "w": 300,
        "h": 160,
        "status": "正常",
    }


class InventoryLayoutTests(unittest.TestCase):
    def test_old_factory_fourth_workshop_first_floor_500_is_required_and_unlimited(self):
        code = "老厂四车间一楼500"

        self.assertIn(code, OLD_FACTORY_SLOT_CODES)
        self.assertIn(code, REQUIRED_SLOT_CODES)
        self.assertEqual(get_slot_capacity(code), UNLIMITED_WAREHOUSE_CAPACITY)

    def test_merge_required_slots_is_idempotent_and_space_insensitive(self):
        existing = [_slot("大机型区域 01"), _slot("A01", 1)]

        first = merge_required_warehouse_slots(existing)
        second = merge_required_warehouse_slots(first)

        normalized = ["".join(str(slot["code"]).split()) for slot in first]
        self.assertEqual(len(first), len(existing) + len(REQUIRED_SLOT_CODES) - 1)
        self.assertEqual(len(normalized), len(set(normalized)))
        self.assertEqual(second, first)
        self.assertIn("大机型区域06", normalized)
        self.assertIn("报废区01", normalized)

    def test_enrich_layout_adds_capacity_without_mutating_stored_layout(self):
        stored = {
            "slots": [
                _slot("A01"),
                _slot("大机型区域06", 1),
                _slot("老厂一车间400", 2),
            ]
        }

        enriched = enrich_warehouse_layout(stored)

        self.assertNotIn("capacity", stored["slots"][0])
        self.assertEqual(enriched["slots"][0]["capacity"], 5)
        self.assertEqual(enriched["slots"][1]["capacity"], LARGE_WAREHOUSE_MAX_CAPACITY)
        self.assertIsNone(enriched["slots"][2]["capacity"])
        self.assertTrue(enriched["slots"][2]["unlimited"])

    def test_merge_preserves_existing_slot_configuration(self):
        existing = [{**_slot("A01"), "status": "锁定", "allowed_models": "V8"}]

        merged = merge_required_warehouse_slots(existing)

        self.assertEqual(merged[0], existing[0])


if __name__ == "__main__":
    unittest.main()
