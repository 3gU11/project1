"""V8 → 云端工厂状态回写必须携带 Spring 统一服务要求的静态认证头。

背景：help 云端把 /api/dealer/orders/{orderNo}/v8-status 路由到统一 Spring 服务
（aftercare-api），该接口校验 X-V7-API-KEY 与 X-V8-Sync-Secret 两个静态头；
V8 之前只发 HMAC 签名头，导致切路由后回写 401。这里锁定请求头契约。

只做内存单测：不连真实 MySQL、不发真实 HTTP。
"""

from __future__ import annotations

import pytest

import crud.cloud_dealer_order_sync as sync


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ok": True}


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url: str, headers: dict | None = None, content: bytes | None = None) -> _FakeResponse:
        self.calls.append({"url": url, "headers": dict(headers or {}), "content": content})
        return _FakeResponse()


def _configure(monkeypatch, *, api_key: str | None = "factory-api-key") -> _FakeClient:
    monkeypatch.setenv("WECHAT_CLOUD_API_BASE", "https://cloud.example")
    monkeypatch.setenv("V8_SYNC_SECRET", "s" * 40)
    if api_key is None:
        monkeypatch.delenv("V7_API_KEY", raising=False)
    else:
        monkeypatch.setenv("V7_API_KEY", api_key)
    fake = _FakeClient()
    monkeypatch.setattr(sync, "_get_http_client", lambda: fake)
    return fake


def test_push_cloud_review_sends_static_factory_auth_headers(monkeypatch):
    fake = _configure(monkeypatch)

    sync.push_cloud_review("DO-1", "rejected", reviewer="系统管理员", note="不发")

    headers = fake.calls[0]["headers"]
    assert headers["X-V7-API-KEY"] == "factory-api-key"
    assert headers["X-V8-Sync-Secret"] == "s" * 40
    # HMAC 签名头仍需保留（桥接等旧链路继续依赖）。
    assert headers.get("X-V8-Signature", "").startswith("sha256=")


def test_push_cloud_status_headers_tolerate_missing_api_key(monkeypatch):
    fake = _configure(monkeypatch, api_key=None)
    # 代码会回退读仓库 .env；这里强制为空，验证“未配置时不发送该头”的兼容分支。
    monkeypatch.setattr(sync, "_read_dotenv_value", lambda key: "")

    sync.push_cloud_contract("DO-1", contract_no="HT-1", operator="系统管理员")

    headers = fake.calls[0]["headers"]
    assert "X-V7-API-KEY" not in headers
    assert headers["X-V8-Sync-Secret"] == "s" * 40
