"""驳回订单「原单重新申请」：V8 本地镜像必须跟随云端重置，且不能把 rejected 反向推回云端。

背景：小程序/云端把被驳回订单恢复成 pending 后，V8 本地 dealer_orders 仍是 rejected，
周期对账会每 60s 把 rejected 再推回云端，用户看到的状态永远改不回来。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text

import crud.cloud_dealer_order_sync as sync
import crud.local_contract_drafts as contract_drafts
import crud.cloud_attachments as cloud_attachments

ORDER_NO = "DO-REAPPLY-1001"

# sync_cloud_dealer_orders 的 UPDATE 分支会写这些列；SQLite 用宽松类型即可。
_DEALER_ORDER_COLUMNS = [
    "dealer_id",
    "dealer_name",
    "dealer_phone",
    "regional_manager_name",
    "customer_name",
    "delivery_address",
    "office_name",
    "office_contact",
    "office_phone",
    "contact_name",
    "contact_phone",
    "model",
    "batch_no",
    "eta",
    "inventory_type",
    "quantity",
    "approved_qty",
    "allocated_qty",
    "delivery_date",
    "remark",
    "extra_remark",
    "ERMQ",
    "factory_pending",
    "source",
    "last_synced_at",
    "sync_status",
    "sync_error",
    "factory_reviewed_at",
    "factory_reviewed_by",
    "extra_remark_reviewed_at",
    "extra_remark_reviewed_by",
    "status",
    "regional_review_status",
    "regional_review_note",
    "regional_reviewed_by",
    "regional_reviewed_at",
    "reviewed_at",
    "reviewed_by",
    "contract_no",
    "v7_order_no",
    "review_note",
    "updated_at",
]


def _make_engine(**values):
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _sqlite_now(dbapi_connection, _record):
        # 生产代码的 UPDATE 里用 MySQL 的 NOW()；SQLite 没有，注册一个等价函数。
        dbapi_connection.create_function("NOW", 0, lambda: "2026-11-09 16:20:00")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE dealer_orders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "order_no TEXT NOT NULL, line_no INTEGER NOT NULL DEFAULT 1, "
                + ", ".join(f"{name} TEXT" for name in _DEALER_ORDER_COLUMNS)
                + ")"
            )
        )
        columns = ["order_no", "line_no", *_DEALER_ORDER_COLUMNS]
        row = {name: None for name in columns}
        row.update({"order_no": ORDER_NO, "line_no": 1, **values})
        conn.execute(
            text(
                "INSERT INTO dealer_orders (" + ", ".join(columns) + ") VALUES ("
                + ", ".join(f":{name}" for name in columns)
                + ")"
            ),
            row,
        )
    return engine


def _patch_sync(monkeypatch, engine, orders):
    monkeypatch.setattr(sync, "ensure_dealer_order_tables", lambda: None)
    monkeypatch.setattr(sync, "get_engine", lambda: engine)
    monkeypatch.setattr(sync, "fetch_cloud_dealer_orders", lambda *args, **kwargs: orders)
    monkeypatch.setattr(contract_drafts, "create_from_order", lambda order: {"_created": False})
    monkeypatch.setattr(
        cloud_attachments,
        "sync_cloud_order_attachments",
        lambda payload: {"orders": 0, "scanned": 0, "synced": 0, "skipped": 0, "failed": 0, "errors": []},
    )


def _cloud_pending_order():
    return {
        "id": ORDER_NO,
        "status": "pending",
        "updated_at": "2026-11-09 16:10:00",
        "items": [
            {
                "lineNo": 1,
                "status": "pending",
                "model": "DK7745",
                "quantity": 2,
                "customer_name": "重新申请后的客户",
                "delivery_address": "浙江省宁波市新地址 8 号",
                "contact_name": "李工",
                "contact_phone": "13900139000",
                "inventory_type": "finished",
                "batch_no": "B1",
            }
        ],
    }


def test_cloud_reapply_pending_resets_local_rejected(monkeypatch):
    engine = _make_engine(
        status="rejected",
        customer_name="旧客户",
        model="DK7745",
        quantity="1",
        reviewed_at="2026-11-09 16:01:31",
        reviewed_by="系统管理员",
        review_note="1",
        contract_no="HT-OLD",
        approved_qty="1",
        allocated_qty="1",
        factory_pending="0",
    )
    _patch_sync(monkeypatch, engine, [_cloud_pending_order()])

    sync.sync_cloud_dealer_orders(status="pending")

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM dealer_orders WHERE order_no=:no"), {"no": ORDER_NO}).mappings().one()
    assert row["status"] == "pending"
    assert not row["reviewed_at"]
    assert not row["reviewed_by"]
    assert not row["review_note"]
    assert not row["contract_no"]
    assert int(row["approved_qty"] or 0) == 0
    assert int(row["allocated_qty"] or 0) == 0
    assert int(row["factory_pending"] or 0) == 0
    assert row["customer_name"] == "重新申请后的客户"
    assert row["delivery_address"] == "浙江省宁波市新地址 8 号"


def test_reconcile_does_not_push_rejected_when_cloud_reapplied_after_review(monkeypatch):
    engine = _make_engine(
        status="rejected",
        allocated_qty="0",
        reviewed_at="2026-11-09 16:01:31",
        reviewed_by="系统管理员",
        review_note="1",
        customer_name="旧客户",
        model="DK7745",
        quantity="1",
        updated_at="2026-11-09 16:01:31",
    )
    monkeypatch.setattr(sync, "ensure_dealer_order_tables", lambda: None)
    monkeypatch.setattr(sync, "get_engine", lambda: engine)
    # 云端在驳回之后被重新申请（updated_at 晚于本地 reviewed_at），当前是 pending。
    monkeypatch.setattr(
        sync,
        "find_cloud_dealer_order",
        lambda order_no: {
            "id": order_no,
            "status": "pending",
            "updated_at": "2026-11-09 16:10:00",
            "items": [{"lineNo": 1, "status": "pending", "model": "DK7745", "quantity": 1,
                       "updated_at": "2026-11-09 16:10:00"}],
        },
    )
    pushed: list[dict] = []
    monkeypatch.setattr(sync, "push_cloud_review", lambda *args, **kwargs: pushed.append(kwargs) or {})

    result = sync.reconcile_local_dealer_order_statuses_to_cloud(10)

    assert result["pushed"] == 0
    assert pushed == []


def test_reconcile_still_repairs_rejected_when_cloud_has_no_newer_apply(monkeypatch):
    engine = _make_engine(
        status="rejected",
        allocated_qty="0",
        reviewed_at="2026-11-09 16:01:31",
        reviewed_by="系统管理员",
        review_note="1",
        model="DK7745",
        quantity="1",
        updated_at="2026-11-09 16:01:31",
    )
    monkeypatch.setattr(sync, "ensure_dealer_order_tables", lambda: None)
    monkeypatch.setattr(sync, "get_engine", lambda: engine)
    # 云端仍旧停留在驳回前的 pending，且更新时间早于本地驳回时间：属于漏推，需要补推。
    monkeypatch.setattr(
        sync,
        "find_cloud_dealer_order",
        lambda order_no: {
            "id": order_no,
            "status": "pending",
            "updated_at": "2026-11-09 15:00:00",
            "items": [{"lineNo": 1, "status": "pending", "model": "DK7745", "quantity": 1,
                       "updated_at": "2026-11-09 15:00:00"}],
        },
    )
    pushed: list[dict] = []
    monkeypatch.setattr(
        sync,
        "push_cloud_review",
        lambda *args, **kwargs: pushed.append({"args": args, "kwargs": kwargs}) or {},
    )

    result = sync.reconcile_local_dealer_order_statuses_to_cloud(10)

    assert result["pushed"] == 1
    assert pushed and pushed[0]["args"][1] == "rejected"
