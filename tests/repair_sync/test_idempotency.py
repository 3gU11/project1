import unittest
from datetime import date

from repair_sync.scheduler import business_key, event_id


class IdempotencyTests(unittest.TestCase):
    def test_business_keys_are_stable_per_date(self):
        target = date(2026, 7, 16)
        self.assertEqual(business_key(target), "repair_snapshot:2026-07-16")
        self.assertEqual(event_id(target), "v8-repair-snapshot-20260716")
        self.assertEqual(event_id(target), event_id(target))


if __name__ == "__main__":
    unittest.main()
