import unittest
from unittest.mock import patch

from ops.repair_order_inventory_sync import (
    apply_repair,
    backup_names,
    require_database_url,
    validate_run_id,
)


class _Transaction:
    def __init__(self):
        self.exited_with = None

    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback):
        self.exited_with = exc_type
        return False


class _Engine:
    def __init__(self):
        self.transaction = _Transaction()

    def begin(self):
        return self.transaction


class RepairOrderInventorySyncTests(unittest.TestCase):
    def test_database_url_must_be_explicit_mysql_url(self):
        with self.assertRaises(SystemExit):
            require_database_url("")
        with self.assertRaises(SystemExit):
            require_database_url("sqlite:///local.db")
        self.assertEqual(
            require_database_url("mysql+pymysql://user:pass@host/db"),
            "mysql+pymysql://user:pass@host/db",
        )

    def test_run_id_and_backup_names_are_bounded(self):
        self.assertEqual(validate_run_id("20260917_182837"), "20260917_182837")
        with self.assertRaises(SystemExit):
            validate_run_id("../../production")
        self.assertEqual(
            backup_names("20260917_182837")["units"],
            "repair_backup_unlogged_bindings_20260917_182837_units",
        )

    @patch("ops.repair_order_inventory_sync.preview_connection")
    @patch("ops.repair_order_inventory_sync.create_backups")
    def test_failed_post_check_exits_transaction_with_error(self, create_backups, preview_connection):
        create_backups.return_value = {"units": "u", "inventory": "i", "mirror": "m"}
        preview_connection.return_value = {
            "unlogged_binding_count": 1,
            "mirror_mismatch_count": 0,
        }
        engine = _Engine()

        with self.assertRaisesRegex(RuntimeError, "rolled back"):
            apply_repair(
                engine,
                "20260917_182837",
                {"unlogged_bindings": [], "mirror_mismatches": []},
            )

        self.assertIs(engine.transaction.exited_with, RuntimeError)


if __name__ == "__main__":
    unittest.main()
