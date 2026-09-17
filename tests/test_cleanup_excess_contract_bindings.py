import unittest

from ops.cleanup_excess_contract_bindings import (
    backup_names,
    candidate_fingerprint,
    classify_candidates,
    require_database_url,
    validate_run_id,
)


def unit(unit_id, *, protected=False, batch="08-12", serial=None, status="待入库"):
    return {
        "unit_id": unit_id,
        "serial_no": serial or unit_id,
        "batch_code": batch,
        "contract_no": "HT-1",
        "model_type": "MODEL-1",
        "sales_id": "SO-1" if protected else "",
        "inventory_order_no": "",
        "is_locked": 0,
        "is_contract_pinned": 0,
        "has_allocation_transaction": int(protected),
        "has_allocation_audit": int(protected),
        "has_inventory": 1,
        "inventory_status": status,
    }


class CleanupExcessContractBindingsTests(unittest.TestCase):
    def test_selects_only_excess_when_planned_quantity_is_protected(self):
        report = classify_candidates(
            [{"contract_no": "HT-1", "model_type": "MODEL-1", "plan_qty": "2"}],
            [unit("kept-1", protected=True), unit("kept-2", protected=True), unit("bad-1")],
        )
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["unit_id"], "bad-1")
        self.assertEqual(report["accepted_groups"][0]["excess_qty"], 1)

    def test_rejects_group_without_enough_allocation_evidence(self):
        report = classify_candidates(
            [{"contract_no": "HT-1", "model_type": "MODEL-1", "plan_qty": 2}],
            [unit("kept-1", protected=True), unit("unknown-1"), unit("unknown-2")],
        )
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(len(report["rejected_over_plan_groups"]), 1)

    def test_rejects_unbatched_or_protected_inventory_rows(self):
        report = classify_candidates(
            [{"contract_no": "HT-1", "model_type": "MODEL-1", "plan_qty": 1}],
            [unit("kept-1", protected=True), unit("no-batch", batch=""), unit("stock", status="库存中（A01）")],
        )
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["rejected_over_plan_groups"][0]["unclassified_qty"], 1)

    def test_fingerprint_is_order_independent_and_content_sensitive(self):
        first = unit("a")
        second = unit("b")
        self.assertEqual(candidate_fingerprint([first, second]), candidate_fingerprint([second, first]))
        self.assertNotEqual(candidate_fingerprint([first]), candidate_fingerprint([second]))

    def test_database_url_and_backup_suffix_are_bounded(self):
        with self.assertRaises(SystemExit):
            require_database_url("")
        with self.assertRaises(SystemExit):
            require_database_url("sqlite:///local.db")
        self.assertEqual(
            require_database_url("mysql+pymysql://user:pass@host/db"),
            "mysql+pymysql://user:pass@host/db",
        )
        with self.assertRaises(SystemExit):
            validate_run_id("../../prod")
        self.assertEqual(
            backup_names("20260917_190000")["units"],
            "repair_backup_excess_contract_20260917_190000_units",
        )


if __name__ == "__main__":
    unittest.main()
