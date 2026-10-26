"""经销商订单状态回写（cancelled / partial_allocated / contracted）的 dispatch 映射测试。

用例只替换 V8 侧的云端 HTTP 出口（_post_cloud_order）与本地订单存在性查询，
不访问真实云端，也不依赖 MySQL，方便在无网络环境回归。
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import create_engine, text

import crud.cloud_dealer_order_sync as sync
import crud.cloud_sync_outbox as outbox


def _make_order_engine(*order_statuses: tuple[str, str]):
    """构造含 order_no/line_no/status 的最小 SQLite 库，供 dispatch 的存在性与聚合状态查询。"""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE dealer_orders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, "
                "line_no INTEGER NOT NULL DEFAULT 1, status TEXT, "
                "allocated_qty INTEGER NOT NULL DEFAULT 0)"
            )
        )
        line_no_by_order: dict[str, int] = {}
        for order_no, status in order_statuses:
            line_no = line_no_by_order.get(order_no, 0) + 1
            line_no_by_order[order_no] = line_no
            conn.execute(
                text(
                    "INSERT INTO dealer_orders (order_no, line_no, status, allocated_qty) "
                    "VALUES (:order_no, :line_no, :status, 0)"
                ),
                {"order_no": order_no, "line_no": line_no, "status": status},
            )
    return engine


def _use_local_order(monkeypatch, *order_statuses: tuple[str, str]):
    """把 dispatch 使用的 get_engine 指向本地 SQLite 订单库。"""
    engine = _make_order_engine(*order_statuses)
    monkeypatch.setattr(outbox, "get_engine", lambda: engine)
    return engine


@pytest.fixture()
def dispatched_calls(monkeypatch):
    """替换云端 HTTP 出口，记录每次实际下发的 payload，避免连接真实云端。"""
    calls: list[dict] = []

    def fake_post_cloud_order(order_no, path_suffix, payload, idempotency_key):
        calls.append(
            {
                "order_no": order_no,
                "path_suffix": path_suffix,
                "payload": payload,
                "idempotency_key": idempotency_key,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(sync, "_post_cloud_order", fake_post_cloud_order)
    return calls


@pytest.fixture()
def existing_order(monkeypatch):
    """本地存在经销商订单，dispatch 不会走“订单已不存在则跳过”分支。"""
    return _use_local_order(monkeypatch, ("DO-1001", "pending"))


@pytest.fixture()
def missing_order(monkeypatch):
    """本地没有对应经销商订单，用于验证取消事件也会被跳过。"""
    return _use_local_order(monkeypatch)


def _dispatch(event_type: str, payload: dict, event_id: str = "event-1") -> None:
    outbox._dispatch_event(
        {
            "event_id": event_id,
            "event_type": event_type,
            "biz_key": str(payload.get("order_no") or ""),
            "payload": payload,
        }
    )


def test_sync_event_types_include_dealer_order_cancelled():
    assert "dealer_order_cancelled" in outbox.SYNC_EVENT_TYPES


def test_cancel_event_dispatch_writes_cancelled_status_and_line_items(existing_order, dispatched_calls):
    _dispatch(
        "dealer_order_cancelled",
        {
            "order_no": "DO-1001",
            "contract_no": "HT202610240001",
            "operator": "alice",
            "note": "合同已取消",
            "line_nos": [1, 2],
        },
        event_id="v8-outbox-dealer_order_cancelled-abc",
    )

    assert len(dispatched_calls) == 1
    call = dispatched_calls[0]
    assert call["order_no"] == "DO-1001"
    assert call["path_suffix"] == "v8-status"
    assert call["idempotency_key"] == "v8-outbox-dealer_order_cancelled-abc"
    payload = call["payload"]
    assert payload["status"] == "cancelled"
    # 按行取消时不回传合同号，避免把云端各行原合同号覆盖成并集；云端 COALESCE 保留原值。
    assert "contractNo" not in payload
    assert payload["reviewedBy"] == "alice"
    assert payload["reviewNote"] == "合同已取消"
    assert payload["items"] == [
        {"lineNo": 1, "status": "cancelled"},
        {"lineNo": 2, "status": "cancelled"},
    ]
    assert payload["updatedAt"]


def test_push_cloud_cancel_without_line_nos_omits_items(dispatched_calls):
    sync.push_cloud_cancel("DO-1001", contract_no="HT-9", operator="system")

    payload = dispatched_calls[0]["payload"]
    assert payload["status"] == "cancelled"
    assert "items" not in payload
    # 整单 + 单一合同：允许回传 contractNo。
    assert payload["contractNo"] == "HT-9"
    assert dispatched_calls[0]["idempotency_key"] == "v8-outbox-cancel-DO-1001-HT-9"


def test_push_cloud_cancel_omits_multi_contract_union(dispatched_calls):
    # 多合同并集不能下发到云端，否则会把每行原合同号污染成「A、B」。
    sync.push_cloud_cancel("DO-1001", contract_no="HT-1、HT-2", operator="system")

    assert "contractNo" not in dispatched_calls[0]["payload"]


def test_push_cloud_cancel_omits_contract_no_for_line_level_cancel(dispatched_calls):
    sync.push_cloud_cancel("DO-1001", contract_no="HT-9", line_nos=[2], operator="system")

    assert "contractNo" not in dispatched_calls[0]["payload"]


def test_push_cloud_cancel_default_idempotency_key_is_ascii_safe(dispatched_calls):
    sync.push_cloud_cancel("DO-1001", contract_no="HT-1、HT-2", operator="system")

    key = dispatched_calls[0]["idempotency_key"]
    assert key.isascii()
    assert "、" not in key


def test_pull_status_rank_matches_push_semantics():
    # 云端只把 cancelled/completed 当终态：completed 允许覆盖 rejected；
    # 下拉合并 rank 必须与推送侧 _ORDER_STATUS_RANK 保持一致，避免长期分歧。
    import crud.cloud_sync_outbox as outbox

    assert sync._status_rank("completed") > sync._status_rank("rejected")
    assert sync._status_rank("cancelled") > sync._status_rank("completed")
    for status in ("pending", "approved", "contracted", "partial_allocated", "allocated", "rejected", "completed", "cancelled"):
        assert outbox._order_status_rank(status) == sync._status_rank(status)


def test_push_cloud_cancel_dedupes_and_skips_invalid_line_nos(dispatched_calls):
    sync.push_cloud_cancel("DO-1001", line_nos=[2, 2, 0, "3", None])

    assert dispatched_calls[0]["payload"]["items"] == [
        {"lineNo": 2, "status": "cancelled"},
        {"lineNo": 3, "status": "cancelled"},
    ]


def test_cancel_event_is_skipped_when_local_order_missing(missing_order, dispatched_calls):
    _dispatch("dealer_order_cancelled", {"order_no": "DO-404", "line_nos": [1]})

    assert dispatched_calls == []


def test_allocated_event_passes_partial_allocated_status(existing_order, dispatched_calls):
    _dispatch(
        "dealer_order_allocated",
        {
            "order_no": "DO-1001",
            "contract_no": "HT-9",
            "operator": "system",
            "v7_order_no": "SO-1",
            "status": "partial_allocated",
        },
        event_id="evt-alloc-partial",
    )

    call = dispatched_calls[0]
    assert call["idempotency_key"] == "evt-alloc-partial"
    assert call["payload"]["status"] == "partial_allocated"
    assert call["payload"]["contractNo"] == "HT-9"
    assert call["payload"]["v7OrderNo"] == "SO-1"


def test_allocated_event_defaults_to_allocated_status(existing_order, dispatched_calls):
    _dispatch("dealer_order_allocated", {"order_no": "DO-1001"})

    assert dispatched_calls[0]["payload"]["status"] == "allocated"


def test_push_cloud_allocate_rejects_unknown_status(dispatched_calls):
    with pytest.raises(ValueError, match="allocated or partial_allocated"):
        sync.push_cloud_allocate("DO-1001", status="completed")
    assert dispatched_calls == []


def test_reviewed_event_passes_contracted_status(existing_order, dispatched_calls):
    _dispatch(
        "dealer_order_reviewed",
        {
            "order_no": "DO-1001",
            "status": "contracted",
            "reviewer": "bob",
            "note": "附加备注复审通过",
        },
        event_id="evt-review-contracted",
    )

    call = dispatched_calls[0]
    assert call["idempotency_key"] == "evt-review-contracted"
    assert call["payload"]["status"] == "contracted"
    assert call["payload"]["reviewedBy"] == "bob"
    assert call["payload"]["reviewNote"] == "附加备注复审通过"


@pytest.mark.parametrize(
    "status",
    ["approved", "rejected", "contracted", "partial_allocated", "allocated", "completed", "pending"],
)
def test_push_cloud_review_accepts_cloud_writable_statuses(dispatched_calls, status):
    sync.push_cloud_review("DO-1001", status, reviewer="bob", note="复审")

    assert dispatched_calls[0]["payload"]["status"] == status


def test_push_cloud_review_rejects_status_outside_cloud_writable_set(dispatched_calls):
    with pytest.raises(ValueError, match="cloud review status"):
        sync.push_cloud_review("DO-1001", "cancelled", reviewer="bob")
    assert dispatched_calls == []


class _FakeCloudResponse:
    def __init__(self, data: list[dict]):
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": self._data}


class _FakeCloudClient:
    """按 /api/v8/bridge/orders?status=... 返回云端真实结构的订单，不发起真实 HTTP 请求。"""

    def __init__(self, orders_by_status: dict[str, list[dict]]):
        self.orders_by_status = orders_by_status

    def get(self, url: str, headers: dict | None = None) -> _FakeCloudResponse:
        status = (parse_qs(urlsplit(url).query).get("status") or [""])[0]
        return _FakeCloudResponse(self.orders_by_status.get(status, []))


def test_fetch_all_dedupes_by_cloud_order_id(monkeypatch):
    # 生产云 /api/v8/bridge/orders 顶层只有 id（= order_no），items 里只有 lineNo，
    # 没有 order_no/orderNo 字段；修复前所有订单去重键都是 ("", 1)，只会返回 1 条。
    cloud_orders = {
        "pending": [{"id": "DO1", "items": [{"lineNo": 1, "status": "pending"}]}],
        "approved": [{"id": "DO2", "items": [{"lineNo": 1, "status": "approved"}]}],
    }
    monkeypatch.setattr(sync, "_cloud_config", lambda: ("https://cloud.example", "api-key"))
    monkeypatch.setattr(sync, "_sync_secret", lambda: "test-bridge-secret-32-bytes-minimum!")
    monkeypatch.setattr(sync, "_get_http_client", lambda: _FakeCloudClient(cloud_orders))

    fetched = sync.fetch_cloud_dealer_orders(status="all")

    assert [order.get("id") for order in fetched] == ["DO1", "DO2"]


# ---------------------------------------------------------------------------
# P1 修复：退避重试中“晚到”的旧事件不得覆盖本地已推进的终态
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (
            "dealer_order_allocated",
            {"order_no": "DO-1001", "status": "allocated", "contract_no": "HT-9"},
        ),
        (
            "dealer_order_reviewed",
            {"order_no": "DO-1001", "status": "approved", "reviewer": "bob"},
        ),
        (
            "dealer_order_contracted",
            {"order_no": "DO-1001", "contract_no": "HT-9", "operator": "bob"},
        ),
        (
            "dealer_order_completed",
            {"order_no": "DO-1001", "contract_no": "HT-9", "operator": "bob"},
        ),
    ],
)
def test_stale_events_are_skipped_when_local_order_cancelled(
    monkeypatch, dispatched_calls, event_type, payload
):
    _use_local_order(monkeypatch, ("DO-1001", "cancelled"))

    _dispatch(event_type, payload, event_id="late-event")

    # 本地已取消（rank 7），旧事件 rank 更低，直接丢弃且不发 HTTP。
    assert dispatched_calls == []


def test_stale_approved_review_is_skipped_when_local_order_contracted(monkeypatch, dispatched_calls):
    _use_local_order(monkeypatch, ("DO-1001", "contracted"))

    _dispatch(
        "dealer_order_reviewed",
        {"order_no": "DO-1001", "status": "approved", "reviewer": "bob"},
        event_id="late-approved",
    )

    assert dispatched_calls == []


def test_stale_allocated_event_is_skipped_when_local_order_completed(monkeypatch, dispatched_calls):
    _use_local_order(monkeypatch, ("DO-1001", "completed"))

    _dispatch(
        "dealer_order_allocated",
        {"order_no": "DO-1001", "status": "allocated"},
        event_id="late-allocated",
    )

    assert dispatched_calls == []


def test_cancel_event_is_never_blocked_by_local_status(monkeypatch, dispatched_calls):
    # 取消事件永远不被本地状态拦截（rank 最高且本地已取消时仍需重试回传）。
    _use_local_order(monkeypatch, ("DO-1001", "cancelled"))

    _dispatch(
        "dealer_order_cancelled",
        {"order_no": "DO-1001", "line_nos": [1]},
        event_id="cancel-retry",
    )

    assert len(dispatched_calls) == 1
    assert dispatched_calls[0]["payload"]["status"] == "cancelled"


def test_same_rank_event_is_still_pushed(monkeypatch, dispatched_calls):
    # 只有 local_rank > intended_rank 才丢弃；同 rank（contract 对 contract）必须继续推送。
    _use_local_order(monkeypatch, ("DO-1001", "contracted"))

    _dispatch(
        "dealer_order_reviewed",
        {"order_no": "DO-1001", "status": "contracted", "reviewer": "bob"},
        event_id="same-rank",
    )

    assert len(dispatched_calls) == 1
    assert dispatched_calls[0]["payload"]["status"] == "contracted"


def test_completed_event_is_pushed_when_local_order_rejected(monkeypatch, dispatched_calls):
    # 云端只把 cancelled/completed 当终态，completed 允许覆盖已驳回，不能被本地跳掉。
    _use_local_order(monkeypatch, ("DO-1001", "rejected"))

    _dispatch(
        "dealer_order_reviewed",
        {"order_no": "DO-1001", "status": "completed", "reviewer": "bob"},
        event_id="completed-after-rejected",
    )

    assert len(dispatched_calls) == 1
    assert dispatched_calls[0]["payload"]["status"] == "completed"


def test_rejected_event_is_skipped_when_local_order_completed(monkeypatch, dispatched_calls):
    _use_local_order(monkeypatch, ("DO-1001", "completed"))

    _dispatch(
        "dealer_order_reviewed",
        {"order_no": "DO-1001", "status": "rejected", "reviewer": "bob"},
        event_id="late-rejected",
    )

    assert dispatched_calls == []


def _make_outbox_engine(rows: list[dict]):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE cloud_sync_outbox ("
                "event_id TEXT PRIMARY KEY, event_type TEXT, biz_key TEXT, status TEXT, "
                "last_error TEXT, updated_at TIMESTAMP)"
            )
        )
        for row in rows:
            conn.execute(
                text(
                    "INSERT INTO cloud_sync_outbox (event_id, event_type, biz_key, status) "
                    "VALUES (:event_id, :event_type, :biz_key, :status)"
                ),
                row,
            )
    return engine


def test_supersede_pending_order_sync_events_only_targets_pending_dealer_events():
    engine = _make_outbox_engine(
        [
            {"event_id": "e1", "event_type": "dealer_order_allocated", "biz_key": "DO-1001", "status": "pending"},
            {"event_id": "e2", "event_type": "dealer_order_reviewed", "biz_key": "DO-1001", "status": "failed"},
            {"event_id": "e3", "event_type": "dealer_order_cancelled", "biz_key": "DO-1001", "status": "pending"},
            {"event_id": "e4", "event_type": "dealer_order_contracted", "biz_key": "DO-1001", "status": "synced"},
            {"event_id": "e5", "event_type": "dealer_order_allocated", "biz_key": "DO-2002", "status": "pending"},
            {"event_id": "e6", "event_type": "wechat_batch_summary_sync", "biz_key": "DO-1001", "status": "pending"},
        ]
    )

    with engine.begin() as conn:
        affected = outbox.supersede_pending_order_sync_events(conn, "DO-1001", reason="cancel wins")
        superseded = conn.execute(
            text(
                "SELECT status, last_error FROM cloud_sync_outbox WHERE event_id='e1'"
            )
        ).mappings().one()
        statuses = {
            row["event_id"]: row["status"]
            for row in conn.execute(text("SELECT event_id, status FROM cloud_sync_outbox")).mappings()
        }

    # 只作废该订单的 pending/failed dealer_order_* 事件（e1/e2/e3）。
    assert affected == 3
    assert superseded["status"] == "superseded"
    assert superseded["last_error"] == "cancel wins"
    assert statuses["e4"] == "synced"
    assert statuses["e5"] == "pending"
    assert statuses["e6"] == "pending"

    # 空订单号不做任何更新，避免误伤 biz_key='' 的事件。
    with engine.begin() as conn:
        assert outbox.supersede_pending_order_sync_events(conn, "") == 0
