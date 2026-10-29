import unittest
from datetime import datetime, timedelta

from crud.sync_channels import channel_for_event_type, compute_channel_state


class ChannelStateTests(unittest.TestCase):
    def test_periodic_channel_is_ok_before_next_deadline(self):
        now = datetime(2026, 10, 28, 12, 0, 0)
        result = compute_channel_state(
            interval_seconds=300,
            last_success_at=now - timedelta(seconds=120),
            now=now,
        )
        self.assertEqual("ok", result["state"])
        self.assertEqual("正常", result["state_label"])
        self.assertEqual("2026-10-28 12:03:00", result["expected_next_at"])
        self.assertEqual(0, result["overdue_seconds"])

    def test_periodic_channel_is_late_within_grace(self):
        now = datetime(2026, 10, 28, 12, 0, 0)
        result = compute_channel_state(
            interval_seconds=300,
            last_success_at=now - timedelta(seconds=300 + 30),
            now=now,
        )
        self.assertEqual("late", result["state"])

    def test_periodic_channel_is_down_after_grace(self):
        now = datetime(2026, 10, 28, 12, 0, 0)
        result = compute_channel_state(
            interval_seconds=300,
            last_success_at=now - timedelta(seconds=300 + 120),
            now=now,
        )
        self.assertEqual("down", result["state"])
        self.assertEqual("超期未同步", result["state_label"])
        self.assertEqual(120, result["overdue_seconds"])

    def test_unknown_channel_without_success(self):
        result = compute_channel_state(interval_seconds=86400, last_success_at=None)
        self.assertEqual("unknown", result["state"])
        self.assertIsNone(result["expected_next_at"])

    def test_event_driven_channel_idle(self):
        result = compute_channel_state(interval_seconds=None, last_success_at=None)
        self.assertEqual("idle", result["state"])
        self.assertEqual("暂无事件", result["state_label"])

    def test_event_driven_channel_pending_and_failed(self):
        now = datetime(2026, 10, 28, 12, 0, 0)
        self.assertEqual(
            "pending",
            compute_channel_state(interval_seconds=None, last_success_at=now, pending=2, now=now)["state"],
        )
        self.assertEqual(
            "failed",
            compute_channel_state(interval_seconds=None, last_success_at=now, failed=1, now=now)["state"],
        )


class EventChannelMappingTests(unittest.TestCase):
    def test_event_types_map_to_expected_channels(self):
        self.assertEqual("factory-snapshot", channel_for_event_type("wechat_batch_summary_sync"))
        self.assertEqual("machine-snapshot", channel_for_event_type("repair_snapshot_sync"))
        self.assertEqual("status-callback", channel_for_event_type("dealer_order_reviewed"))
        self.assertEqual("status-callback", channel_for_event_type("dealer_order_completed"))
        self.assertIsNone(channel_for_event_type("unknown_event"))


if __name__ == "__main__":
    unittest.main()
