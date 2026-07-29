import unittest
from unittest.mock import MagicMock, patch

from crud.inbound_history import notify_inbound_completion


class InboundCompletionNotifyTests(unittest.TestCase):
    @patch("crud.inbound_history.httpx.Client")
    def test_notifies_scheduling_service_with_unique_serials(self, client_cls):
        response = MagicMock()
        response.json.return_value = {
            "completed_batches": [{"batch_id": "batch-1", "line_id": "line-1"}]
        }
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = response

        completed = notify_inbound_completion(
            [" 96-07-001 ", "96-07-001", "96-07-002", ""],
            operator="tester",
        )

        self.assertEqual(completed, [{"batch_id": "batch-1", "line_id": "line-1"}])
        response.raise_for_status.assert_called_once_with()
        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["json"], {"serial_nos": ["96-07-001", "96-07-002"]})
        self.assertEqual(kwargs["headers"]["X-Username"], "tester")
        self.assertEqual(kwargs["headers"]["X-Role"], "Admin")

    @patch("crud.inbound_history.httpx.Client")
    def test_notification_failure_does_not_fail_inbound(self, client_cls):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = RuntimeError("service unavailable")

        self.assertEqual(notify_inbound_completion(["96-07-001"]), [])

    @patch("crud.inbound_history.httpx.Client")
    def test_empty_serials_are_noop(self, client_cls):
        self.assertEqual(notify_inbound_completion(["", "  "]), [])
        client_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
