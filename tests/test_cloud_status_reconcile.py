"""订单状态回传对账（补发）与完成事件可重试性的单元测试。

不连 MySQL、不连云端：本地订单库与 outbox 表用 SQLite 构造，
实际入队用 monkeypatch 记录参数。"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

import crud.cloud_dealer_order_sync as sync
import crud.cloud_sync_outbox as outbox


def _make_engine(orders: list[dict], events: list[dict]):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE dealer_orders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, "
                "line_no INTEGER NOT NULL DEFAULT 1, status TEXT, "
                "allocated_qty INTEGER NOT NULL DEFAULT 0, contract_no TEXT, "
                "v7_order_no TEXT, updated_at TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE cloud_sync_outbox ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, event_type TEXT, "
                "biz_key TEXT, payload_json TEXT, status TEXT, retry_count INTEGER DEFAULT 0, "
                "last_error TEXT, next_retry_at TIMESTAMP, updated_at TIMESTAMP)"
            )
        )
        for index, row in enumerate(orders):
            conn.execute(
                text(
                    "INSERT INTO dealer_orders "
                    "(order_no, line_no, status, allocated_qty, contract_no, v7_order_no, updated_at) "
                    "VALUES (:order_no, :line_no, :status, :allocated_qty, :contract_no, :v7_order_no, :updated_at)"
                ),
                {
                    "order_no": row["order_no"],
                    "line_no": row.get("line_no", 1),
                    "status": row.get("status", "pending"),
                    "allocated_qty": row.get("allocated_qty", 0),
                    "contract_no": row.get("contract_no", ""),
                    "v7_order_no": row.get("v7_order_no", ""),
                    "updated_at": row.get("updated_at", "2026-11-03 10:00:00"),
                },
            )
        for index, row in enumerate(events):
            conn.execute(
                text(
                    "INSERT INTO cloud_sync_outbox "
                    "(event_id, event_type, biz_key, payload_json, status, updated_at) "
                    "VALUES (:event_id, :event_type, :biz_key, :payload_json, :status, :updated_at)"
                ),
                {
                    "event_id": row.get("event_id", f"event-{index + 1}"),
                    "event_type": row["event_type"],
                    "biz_key": row["biz_key"],
                    "payload_json": json.dumps(row.get("payload") or {}, ensure_ascii=False),
                    "status": row.get("status", "synced"),
                    "updated_at": row.get("updated_at", "2026-11-03 10:00:00"),
                },
            )
    return engine


def _setup(monkeypatch, orders: list[dict], events: list[dict]):
    engine = _make_engine(orders, events)
    monkeypatch.setattr(outbox, "get_engine", lambda: engine)
    monkeypatch.setattr(outbox, "ensure_cloud_sync_outbox_table", lambda: None)
    monkeypatch.setattr(outbox, "cloud_bridge_enabled", lambda: True)
    calls: list[dict] = []

    def fake_insert(conn, event_id, event_type, biz_key, payload_json):
        calls.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "biz_key": biz_key,
                "payload": json.loads(payload_json),
            }
        )

    monkeypatch.setattr(outbox, "insert_cloud_sync_event", fake_insert)
    return engine, calls


def _synced(event_type: str, payload: dict, order_no: str = "DO-R1") -> dict:
    return {"event_type": event_type, "biz_key": order_no, "payload": payload, "status": "synced"}


def test_reconcile_enqueues_when_local_status_ahead_of_last_synced_event(monkeypatch):
    """本地已转合同、最近一次成功回传还是 approved：补发 contracted。"""
    _engine, calls = _setup(
        monkeypatch,
        [
            {
                "order_no": "DO-R1",
                "status": "contracted",
                "contract_no": "HT-202611030001",
                "updated_at": "2026-11-03 10:00:00",
            }
        ],
        [_synced("dealer_order_reviewed", {"status": "approved"})],
    )

    summary = outbox.reconcile_dealer_order_statuses()

    assert summary["enqueued"] == 1
    assert summary["scanned"] == 1
    assert calls[0]["event_type"] == "dealer_order_contracted"
    assert calls[0]["biz_key"] == "DO-R1"
    assert calls[0]["payload"]["contract_no"] == "HT-202611030001"
    assert calls[0]["event_id"].startswith("v8-outbox-reconcile-")


def test_reconcile_skips_when_last_synced_event_already_matches(monkeypatch):
    _engine, calls = _setup(
        monkeypatch,
        [{"order_no": "DO-R1", "status": "contracted", "contract_no": "HT-1"}],
        [_synced("dealer_order_contracted", {"contract_no": "HT-1"})],
    )

    summary = outbox.reconcile_dealer_order_statuses()

    assert summary["enqueued"] == 0
    assert calls == []


@pytest.mark.parametrize("active_status", ["pending", "processing", "failed", "rejected"])
def test_reconcile_skips_orders_with_active_or_retrying_events(monkeypatch, active_status):
    """退避重试中/等待人工重放的事件会自己收尾，对账不再叠一条。"""
    event = _synced("dealer_order_reviewed", {"status": "approved"})
    event["status"] = active_status
    _engine, calls = _setup(
        monkeypatch,
        [{"order_no": "DO-R1", "status": "contracted", "contract_no": "HT-1"}],
        [event],
    )

    assert outbox.reconcile_dealer_order_statuses()["enqueued"] == 0
    assert calls == []


def test_reconcile_skips_orders_never_written_back(monkeypatch):
    """从云端拉下来的历史订单没有回传历史，不主动反向推送。"""
    _engine, calls = _setup(
        monkeypatch,
        [{"order_no": "DO-CLOUD", "status": "approved"}],
        [],
    )

    summary = outbox.reconcile_dealer_order_statuses()

    assert summary["enqueued"] == 0
    assert summary["scanned"] == 1
    assert calls == []


def test_reconcile_skips_pending_orders(monkeypatch):
    _engine, calls = _setup(
        monkeypatch,
        [{"order_no": "DO-R1", "status": "pending"}],
        [_synced("dealer_order_reviewed", {"status": "approved"})],
    )

    assert outbox.reconcile_dealer_order_statuses()["enqueued"] == 0
    assert calls == []


def test_reconcile_enqueues_cancelled_for_whole_cancelled_order(monkeypatch):
    _engine, calls = _setup(
        monkeypatch,
        [
            {"order_no": "DO-R2", "line_no": 1, "status": "cancelled", "contract_no": "HT-2"},
            {"order_no": "DO-R2", "line_no": 2, "status": "cancelled", "contract_no": "HT-2"},
        ],
        [_synced("dealer_order_contracted", {"contract_no": "HT-2"}, order_no="DO-R2")],
    )

    summary = outbox.reconcile_dealer_order_statuses()

    assert summary["enqueued"] == 1
    assert calls[0]["event_type"] == "dealer_order_cancelled"
    assert calls[0]["payload"]["contract_no"] == "HT-2"
    assert "line_nos" not in calls[0]["payload"]


def test_reconcile_disabled_when_cloud_bridge_disabled(monkeypatch):
    _engine, calls = _setup(
        monkeypatch,
        [{"order_no": "DO-R1", "status": "contracted"}],
        [_synced("dealer_order_reviewed", {"status": "approved"})],
    )
    monkeypatch.setattr(outbox, "cloud_bridge_enabled", lambda: False)

    summary = outbox.reconcile_dealer_order_statuses()

    assert summary["enqueued"] == 0
    assert summary["skipped_reason"] == "cloud bridge disabled"
    assert calls == []


def test_completed_dispatch_raises_when_cloud_order_not_readable(monkeypatch):
    """云端暂时读不到订单时不能把完成事件记成 synced，否则永远不会再补发。"""
    engine = _make_engine(
        [{"order_no": "DO-R3", "status": "contracted", "contract_no": "HT-3"}],
        [],
    )
    monkeypatch.setattr(outbox, "get_engine", lambda: engine)
    monkeypatch.setattr(sync, "find_cloud_dealer_order", lambda order_no: None)

    with pytest.raises(RuntimeError, match="completed sync skipped"):
        outbox._dispatch_event(
            {
                "event_id": "evt-completed",
                "event_type": "dealer_order_completed",
                "biz_key": "DO-R3",
                "payload": {"order_no": "DO-R3", "contract_no": "HT-3"},
            }
        )


def test_retry_failed_cloud_sync_events_also_requeues_rejected(monkeypatch):
    engine = _make_engine([], [])
    with engine.begin() as conn:
        for event_id, status in (("e1", "failed"), ("e2", "rejected"), ("e3", "synced")):
            conn.execute(
                text(
                    "INSERT INTO cloud_sync_outbox (event_id, event_type, biz_key, payload_json, status) "
                    "VALUES (:event_id, 'dealer_order_reviewed', 'DO-R4', '{}', :status)"
                ),
                {"event_id": event_id, "status": status},
            )
    monkeypatch.setattr(outbox, "get_engine", lambda: engine)
    monkeypatch.setattr(outbox, "ensure_cloud_sync_outbox_table", lambda: None)

    assert outbox.retry_failed_cloud_sync_events() == {"queued": 2}
    with engine.begin() as conn:
        rows = {
            row["event_id"]: row["status"]
            for row in conn.execute(
                text("SELECT event_id, status FROM cloud_sync_outbox")
            ).mappings()
        }
    assert rows == {"e1": "pending", "e2": "pending", "e3": "synced"}
