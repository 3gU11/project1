import unittest

from ops.repair_kanban_binding_anomalies import (
    CLEAR_ALL,
    CLEAR_UNITS,
    ORDER_ONLY,
    backup_names,
    fingerprint,
    require_database_url,
    validate_run_id,
)


class RepairKanbanBindingAnomaliesTests(unittest.TestCase):
    def test_incident_manifest_has_unique_thirteen_targets(self):
        serials = set(ORDER_ONLY) | set(CLEAR_ALL)
        self.assertEqual(len(serials), len(ORDER_ONLY) + len(CLEAR_ALL))
        self.assertEqual(len(serials) + len(CLEAR_UNITS), 13)

    def test_fingerprint_changes_with_action(self):
        row = {"action": "clear_order", "unit_id": "u", "serial_no": "s", "contract_no": "c", "sales_id": "o"}
        changed = {**row, "action": "clear_all"}
        self.assertNotEqual(fingerprint([row]), fingerprint([changed]))

    def test_database_url_and_run_id_are_bounded(self):
        with self.assertRaises(SystemExit):
            require_database_url("")
        with self.assertRaises(SystemExit):
            require_database_url("sqlite:///test.db")
        self.assertEqual(validate_run_id("20260918_120000"), "20260918_120000")
        with self.assertRaises(SystemExit):
            validate_run_id("../../bad")
        self.assertIn("20260918_120000", backup_names("20260918_120000")["units"])


if __name__ == "__main__":
    unittest.main()
