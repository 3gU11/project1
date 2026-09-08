import unittest
from datetime import date

from repair_sync.snapshot_builder import SnapshotValidationError, build_snapshot_from_rows


class SnapshotBuilderTests(unittest.TestCase):
    def setUp(self):
        self.rows = {
            "machines": [{"machine_no": "M-1", "model_name": "MODEL-1", "customer": "secret"}],
            "materials": [{"material_code": "MAT-1", "material_name": "Part", "material_type": "component"}],
            "materialInstances": [{"component_serial_no": "SN-1", "material_code": "MAT-1"}],
            "machineMaterialBindings": [{
                "machine_no": "M-1", "component_serial_no": "SN-1", "position_code": "P-1",
                "position_name": "Left", "material_code": "MAT-1", "active": 1, "check_status": "passed",
            }],
            "modelDictionary": [{"model_name": "MODEL-1", "model_family": "G", "enabled": 1}],
            "photoItemLibrary": [{"position_code": "P-1", "item_name": "Left", "enabled": 1}],
            "modelPhotoConfig": [{"model_name": "MODEL-1", "position_code": "P-1", "required": 1}],
        }

    def test_build_is_deterministic_and_excludes_sensitive_fields(self):
        first = build_snapshot_from_rows(date(2026, 7, 16), self.rows, snapshot_id="snapshot-1")
        second = build_snapshot_from_rows(date(2026, 7, 16), self.rows, snapshot_id="snapshot-1")
        self.assertEqual(first["recordsSha256"], second["recordsSha256"])
        self.assertEqual(first["tables"]["machines"][0]["customer"], "")
        self.assertNotIn("secret", str(first))
        self.assertEqual(first["counts"]["bindings"], 1)

    def test_active_unapproved_binding_rejects_whole_snapshot(self):
        self.rows["machineMaterialBindings"][0]["check_status"] = "pending"
        with self.assertRaises(SnapshotValidationError):
            build_snapshot_from_rows(date(2026, 7, 16), self.rows)

    def test_binding_rows_can_supply_denormalized_material_data(self):
        rows = dict(self.rows)
        rows["machines"] = rows["machineMaterialBindings"]
        rows["materials"] = []
        rows["materialInstances"] = []
        rows["machines"][0].update({"model_name": "MODEL-1", "material_code": "MAT-1", "material_name": "Part"})
        snapshot = build_snapshot_from_rows(date(2026, 7, 16), rows)
        self.assertEqual(snapshot["counts"]["materials"], 1)
        self.assertEqual(snapshot["counts"]["materialInstances"], 1)

    def test_same_serial_can_be_reused_for_different_material_codes(self):
        rows = self.rows
        rows["materials"].append({"material_code": "MAT-2", "material_name": "Other Part"})
        rows["materialInstances"].append({"component_serial_no": "SN-1", "material_code": "MAT-2"})
        rows["machineMaterialBindings"].append({
            "machine_no": "M-1", "component_serial_no": "SN-1", "material_code": "MAT-2",
            "position_code": "P-2", "position_name": "Right", "active": 1, "check_status": "passed",
        })
        snapshot = build_snapshot_from_rows(date(2026, 7, 16), rows)
        self.assertEqual(snapshot["counts"]["materialInstances"], 2)


if __name__ == "__main__":
    unittest.main()
