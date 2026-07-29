import asyncio
import unittest

from api.websockets.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_from_sync_uses_connection_event_loop(self):
        manager = ConnectionManager()
        socket = FakeWebSocket()
        await manager.connect(socket)

        manager.broadcast_from_sync({"type": "WAREHOUSE_LAYOUT_UPDATE"})
        await asyncio.sleep(0)

        self.assertEqual(socket.messages, [{"type": "WAREHOUSE_LAYOUT_UPDATE"}])


if __name__ == "__main__":
    unittest.main()
