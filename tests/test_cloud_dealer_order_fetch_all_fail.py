"""云端拉单：全部状态都失败时必须抛出可观测错误，不能静默返回空列表。

背景：fetch_cloud_dealer_orders(status="all") 在 ThreadPoolExecutor 里逐状态
catch 异常后只记 warning；当云端基址不可达（例如 [WinError 10061]）导致所有
状态都失败时仍返回 []，上层「立即拉取订单」误报「拉取完成：新增 0」，
定时拉单也把失败记成 last_success_at。本文件用 monkeypatch 替换单状态拉取，
不连 MySQL、不发真实 HTTP。
"""

from __future__ import annotations

import pytest

import crud.cloud_dealer_order_sync as sync

_CONNECTION_ERROR_TEXT = "[WinError 10061] 由于目标计算机积极拒绝，无法连接。"


def _patch_by_status(monkeypatch, outcomes: dict[str, object]) -> list[str]:
    """按 status 返回预设结果；value 为 Exception 实例时抛出，否则当作订单列表。

    返回实际被调用的状态列表，用于确认并发分支确实覆盖了全部云端可读状态。
    """
    calls: list[str] = []

    def fake_fetch(status: str, page_size: int = 100, max_pages: int = 20):
        calls.append(status)
        outcome = outcomes.get(status)
        if isinstance(outcome, BaseException):
            raise outcome
        return list(outcome or [])

    monkeypatch.setattr(sync, "_fetch_cloud_dealer_orders_by_status", fake_fetch)
    return calls


def test_all_statuses_fail_raises_runtime_error_with_underlying_error(monkeypatch):
    calls = _patch_by_status(
        monkeypatch,
        {status: ConnectionError(_CONNECTION_ERROR_TEXT) for status in sync.CLOUD_READ_STATUSES},
    )

    with pytest.raises(RuntimeError) as excinfo:
        sync.fetch_cloud_dealer_orders(status="all")

    message = str(excinfo.value)
    assert "cloud order fetch failed for all statuses" in message
    # 必须带上底层异常文本，否则用户仍看不到真实的连接失败原因。
    assert "WinError 10061" in message
    assert len(calls) == len(sync.CLOUD_READ_STATUSES)


def test_one_status_fails_and_others_return_orders_returns_partial_orders(monkeypatch):
    _patch_by_status(
        monkeypatch,
        {
            "pending": [
                {"id": "DO-PENDING", "items": [{"lineNo": 1, "status": "pending"}]}
            ],
            "approved": [
                {"id": "DO-APPROVED", "items": [{"lineNo": 1, "status": "approved"}]}
            ],
            "contracted": ConnectionError(_CONNECTION_ERROR_TEXT),
        },
    )

    fetched = sync.fetch_cloud_dealer_orders(status="all")

    # 只要有一个状态成功，就维持原有「返回部分结果」行为，不抛错。
    assert [order.get("id") for order in fetched] == ["DO-PENDING", "DO-APPROVED"]


def test_all_statuses_succeed_with_empty_data_returns_empty_list(monkeypatch):
    _patch_by_status(monkeypatch, {status: [] for status in sync.CLOUD_READ_STATUSES})

    # 云端正常返回空数据不是故障，不能抛错。
    assert sync.fetch_cloud_dealer_orders(status="all") == []


def test_one_status_fails_and_only_success_is_empty_does_not_raise(monkeypatch):
    # 只要有一个状态成功（哪怕云端就是空的），就仍是“拉取成功”，不能误报全失败。
    _patch_by_status(
        monkeypatch,
        {"pending": [], "approved": ConnectionError(_CONNECTION_ERROR_TEXT)},
    )

    assert sync.fetch_cloud_dealer_orders(status="all") == []
