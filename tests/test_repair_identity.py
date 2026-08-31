from datetime import date, datetime
import unittest

from crud.repair_identity import to_repair_identity


class RepairIdentityProjectionTest(unittest.TestCase):
    def test_keeps_position_material_and_component_serial_as_distinct_values(self):
        result = to_repair_identity({
            "binding_key": "V8-96-06-234-SN-CPU",
            "machine_no": "96-06-234",
            "model_name": "FR-400XS(PRO)",
            "position_code": "SN-CPU",
            "position_name": "CPU板编号",
            "material_code": "V8-SN-CPU",
            "material_name": "CPU板编号",
            "component_serial_no": "JQ242025-834",
            "delivery_date": date(2026, 7, 13),
            "updated_at": datetime(2026, 8, 1, 15, 41, 57),
        })

        self.assertEqual("96-06-234", result["machineNo"])
        self.assertEqual("SN-CPU", result["positionCode"])
        self.assertEqual("JQ242025-834", result["materialSuffix"])
        self.assertEqual("SN-CPU-JQ242025-834", result["materialCode"])
        self.assertEqual("JQ242025-834", result["componentSerialNo"])
        self.assertEqual("SN-CPU-JQ242025-834", result["uniqueItemId"])
        self.assertEqual("2026-07-13", result["deliveryDate"])
        self.assertEqual("ACTIVE", result["bindingStatus"])

    def test_does_not_reuse_the_position_prefix_as_a_complete_material_code(self):
        result = to_repair_identity({
            "position_code": "SN-CPU",
            "material_code": "V8-SN-CPU",
            "component_serial_no": "KQ201205-0761",
        })

        self.assertNotEqual(result["positionCode"], result["materialCode"])
        self.assertEqual("SN-CPU-KQ201205-0761", result["materialCode"])


if __name__ == "__main__":
    unittest.main()
