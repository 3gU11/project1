import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import api.main as main_module


async def _idle_loop() -> None:
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        raise


class V8SyncStartupWiringTests(unittest.TestCase):
    def test_startup_wires_v8_sync_and_shutdown_cancels_it(self):
        startup_result = {"status": "created", "event_id": "v8-repair-snapshot-20261028-abc"}
        run_startup_sync = AsyncMock(return_value=startup_result)
        run_sync_loop = AsyncMock(side_effect=_idle_loop)

        async def scenario():
            await main_module.on_startup()
            task = getattr(main_module.app.state, "v8_sync_task", None)
            self.assertIsNotNone(task)
            for _ in range(3):
                await asyncio.sleep(0)
            self.assertEqual(startup_result, main_module.app.state.v8_sync_startup_result)
            run_startup_sync.assert_awaited_once()
            run_sync_loop.assert_awaited_once()
            await main_module.on_shutdown()

        with (
            patch("contract_bridge.worker.worker_loop", new=AsyncMock(side_effect=_idle_loop)),
            patch("database.init_mysql_tables_v2", return_value={"initialized": False}),
            patch("crud.cloud_sync_outbox.ensure_cloud_sync_outbox_table"),
            patch("crud.cloud_sync_outbox.cloud_sync_worker_loop", new=AsyncMock(side_effect=_idle_loop)),
            patch(
                "crud.cloud_dealer_order_sync.cloud_pull_worker_loop",
                new=AsyncMock(side_effect=_idle_loop),
            ),
            patch.object(main_module, "watch_dealer_orders_db", new=AsyncMock(side_effect=_idle_loop)),
            patch.object(main_module, "watch_finished_goods_db", new=AsyncMock(side_effect=_idle_loop)),
            patch.object(
                main_module, "cloud_snapshot_heartbeat_loop", new=AsyncMock(side_effect=_idle_loop)
            ),
            patch("v8_sync.scheduler.run_startup_sync", new=run_startup_sync),
            patch("v8_sync.scheduler.run_sync_loop", new=run_sync_loop),
        ):
            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
