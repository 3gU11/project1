import asyncio
import os
import unittest
from unittest.mock import patch

from v8_sync.config import V8SyncConfig
from v8_sync.scheduler import run_startup_sync


class StartupSyncTest(unittest.TestCase):
    def test_disabled_config_does_not_build_snapshot(self):
        with patch("v8_sync.scheduler.run_daily") as run_daily:
            result = asyncio.run(run_startup_sync(V8SyncConfig(enabled=False)))

        self.assertEqual({"status": "disabled"}, result)
        run_daily.assert_not_called()

    def test_demo_mode_does_not_build_snapshot(self):
        with patch.dict(os.environ, {"V8_DEMO_MODE": "1"}), patch("v8_sync.scheduler.run_daily") as run_daily:
            result = asyncio.run(run_startup_sync(V8SyncConfig(enabled=True)))

        self.assertEqual({"status": "demo_disabled"}, result)
        run_daily.assert_not_called()

    def test_invalid_enabled_config_does_not_enqueue(self):
        with patch("v8_sync.scheduler.run_daily") as run_daily:
            result = asyncio.run(run_startup_sync(V8SyncConfig(enabled=True)))

        self.assertEqual({"status": "not_configured"}, result)
        run_daily.assert_not_called()

    def test_enabled_config_runs_one_startup_snapshot(self):
        expected = {"status": "created", "event_id": "startup-event"}
        with patch("v8_sync.scheduler.run_daily", return_value=expected) as run_daily:
            result = asyncio.run(
                run_startup_sync(
                    V8SyncConfig(
                        enabled=True,
                        base_url="https://ruijuncare.rjzkapp.com",
                        key_id="key",
                        hmac_secret="secret",
                    )
                )
            )

        self.assertEqual(expected, result)
        run_daily.assert_called_once()
