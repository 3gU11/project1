"""Regression tests for the sandbox proxy ignoring invalid system proxies.

A malformed HTTP_PROXY/HTTPS_PROXY/ALL_PROXY value used to make the module-level
httpx.AsyncClient constructor raise ``httpx.InvalidURL: Invalid port: ':1]'``,
which turned every /api/v1/sandbox/* call into a 500. The Go sandbox service is
always reached over loopback, so the proxy must never inherit host proxy
settings.
"""
import asyncio

import api.routes.sandbox as sandbox

BAD_PROXY = "http://127.0.0.1::1]"
PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def _set_invalid_proxy_env(monkeypatch) -> None:
    for name in PROXY_ENV_VARS:
        monkeypatch.setenv(name, BAD_PROXY)


def test_get_client_ignores_invalid_system_proxy(monkeypatch):
    _set_invalid_proxy_env(monkeypatch)
    # asyncio.run() creates a fresh event loop per call. Replace the module
    # lock so the shared one is never bound to that temporary loop, and make
    # sure the test starts and ends without a cached client.
    monkeypatch.setattr(sandbox, "_client_lock", asyncio.Lock())
    monkeypatch.setattr(sandbox, "_client", None)

    async def exercise():
        client = None
        try:
            client = await sandbox._get_client()
            assert client.trust_env is False
            assert str(client.base_url).rstrip("/") == sandbox.GO_SANDBOX_URL
            # _reset_client builds a second client; it must be proxy-free too.
            client = await sandbox._reset_client(client)
            assert client.trust_env is False
        finally:
            current = sandbox._client
            sandbox._client = None
            sandbox._client_refs.clear()
            sandbox._retired_clients.clear()
            if current is not None and not current.is_closed:
                await current.aclose()

    # Must not raise httpx.InvalidURL even though the env proxies are invalid.
    asyncio.run(exercise())

    assert sandbox._client is None


class _FakeGoWebSocket:
    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        if False:  # pragma: no cover - makes this an async generator
            yield ""

    async def send(self, data):
        return None


class _FakeClientWebSocket:
    query_params = {"token": "test-token"}

    async def accept(self):
        return None

    async def close(self, code=1000, reason=""):
        return None

    async def receive_text(self):
        raise Exception("client disconnected")

    async def send_text(self, data):
        return None


class _FakeConnect:
    def __init__(self, uri, **kwargs):
        self.uri = uri
        self.kwargs = kwargs

    async def __aenter__(self):
        return _FakeGoWebSocket()

    async def __aexit__(self, *exc_info):
        return False


def test_proxy_ws_disables_system_proxy(monkeypatch):
    _set_invalid_proxy_env(monkeypatch)
    captured = {}

    def fake_connect(uri, **kwargs):
        captured["uri"] = uri
        captured["kwargs"] = kwargs
        return _FakeConnect(uri, **kwargs)

    monkeypatch.setattr(
        sandbox, "get_current_user_context",
        lambda token: {"username": "proxy-test", "role": "Admin"},
    )
    monkeypatch.setattr(sandbox, "get_role_permissions", lambda role: ["SANDBOX_VIEW"])
    monkeypatch.setattr(sandbox.websockets, "connect", fake_connect)

    asyncio.run(asyncio.wait_for(sandbox.proxy_ws(_FakeClientWebSocket()), timeout=5))

    kwargs = captured["kwargs"]
    if sandbox._WS_CONNECT_SUPPORTS_PROXY:
        # websockets 15+ reads proxy env vars by default; None opts out.
        assert kwargs["proxy"] is None
    else:
        assert "proxy" not in kwargs
    assert captured["uri"].endswith("/ws")
    assert ("X-Username", "proxy-test") in kwargs["additional_headers"]
