import unittest
from datetime import date

from unittest.mock import patch
from contextlib import nullcontext

from v8_sync.scheduler import business_key, event_id, revision_event_id, run_daily
from v8_sync.config import V8SyncConfig


class IdempotencyTests(unittest.TestCase):
    def test_business_keys_are_stable_per_date(self):
        target = date(2026, 7, 16)
        self.assertEqual(business_key(target), "repair_snapshot:2026-07-16")
        self.assertEqual(event_id(target), "v8-repair-snapshot-20260716")
        self.assertEqual(event_id(target), event_id(target))

    def test_reuploaded_snapshot_event_key_includes_the_saved_payload_digest(self):
        target = date(2026, 7, 16)
        digest = "0123456789abcdef" + "0" * 48
        snapshot = {
            "snapshot_id": "saved-snapshot",
            "status": "uploaded",
            "payload_sha256": digest,
        }
        with (
            patch("v8_sync.scheduler.advisory_lock", return_value=nullcontext(True)),
            patch("v8_sync.scheduler.run_snapshot", return_value={
                "status": "existing",
                "snapshot": snapshot,
                "payload": {"snapshotId": "generated-snapshot"},
            }),
            patch("v8_sync.scheduler.enqueue_snapshot_event") as enqueue,
        ):
            run_daily(target, config=V8SyncConfig(enabled=True))

        enqueue.assert_called_once_with(
            target,
            "saved-snapshot",
            digest,
            revision=True,
        )
        self.assertEqual(revision_event_id(target, digest), "v8-repair-snapshot-20260716-0123456789abcdef")


if __name__ == "__main__":
    unittest.main()
