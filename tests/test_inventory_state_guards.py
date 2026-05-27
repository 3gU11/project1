import pandas as pd
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from fastapi import Request

from api.routes.inventory import ShippingActionPayload, confirm_shipping, revert_shipping, update_inventory


def test_update_inventory_rejects_oversized_payload():
    payload = [{"流水号": f"SN{i:05d}", "机型": "FR-400G"} for i in range(20001)]

    with pytest.raises(HTTPException) as exc:
        update_inventory(payload, request=MagicMock(spec=Request), current_user={"username": "tester"})

    assert exc.value.status_code == 413
    assert "单次最多允许更新" in str(exc.value.detail)


def test_confirm_shipping_allows_pending_inbound_state(monkeypatch):
    import api.routes.inventory as inventory_route

    saved = {}

    # Mock connection and execution since confirm_shipping queries raw SQL directly
    mock_conn = MagicMock()
    
    mock_result_select = MagicMock()
    mock_result_select.mappings.return_value.all.return_value = [
        {"流水号": "SN001", "状态": "待入库", "更新时间": "", "占用订单号": "SO-001"}
    ]
    
    mock_result_update = MagicMock()
    mock_result_update.rowcount = 1
    
    mock_conn.execute.side_effect = [mock_result_select, mock_result_update]
    
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_engine.begin.return_value.__exit__ = lambda self, *args: None
    
    monkeypatch.setattr(inventory_route, "get_engine", lambda: mock_engine)
    monkeypatch.setattr(
        inventory_route,
        "get_orders",
        lambda: pd.DataFrame([{"订单号": "SO-001", "需求机型": "Model A:1", "需求数量": 1, "status": "active"}]),
    )
    monkeypatch.setattr(inventory_route, "save_orders", lambda df: None)
    monkeypatch.setattr(inventory_route, "archive_shipped_data", lambda df: saved.setdefault("df", df.copy()))
    monkeypatch.setattr(inventory_route, "append_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(inventory_route, "append_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(inventory_route, "enqueue_wechat_batch_summary_sync", lambda *args: None)
    monkeypatch.setattr(inventory_route, "sync_dealer_order_statuses_by_sales_orders", lambda *args: [])

    result = confirm_shipping(
        ShippingActionPayload(serial_nos=["SN001"]),
        request=MagicMock(spec=Request),
        current_operator="tester",
        current_user={"username": "tester"}
    )

    assert result["message"] == "发货完成，共 1 台"
    assert saved["df"].iloc[0]["状态"] == "已出库"


def test_revert_shipping_returns_machine_to_pending_inbound(monkeypatch):
    import api.routes.inventory as inventory_route

    reverted = {}
    monkeypatch.setattr(
        inventory_route,
        "revert_to_inbound",
        lambda sns, reason="", operator=None: reverted.update(
            {"sns": sns, "reason": reason, "operator": operator}
        ),
    )

    result = revert_shipping(
        ShippingActionPayload(serial_nos=["SN001", "SN002"]),
        request=MagicMock(spec=Request),
        current_operator="tester",
        current_user={"username": "tester"}
    )

    assert result == {"message": "已撤回，共 2 台"}
    assert reverted == {
        "sns": ["SN001", "SN002"],
        "reason": "正式发货撤回",
        "operator": "tester",
    }


@pytest.mark.xfail(reason="当前发货确认接口尚未拦截已出库机台的重复发货")
def test_confirm_shipping_rejects_already_shipped_machine(monkeypatch):
    import api.routes.inventory as inventory_route

    monkeypatch.setattr(
        inventory_route,
        "get_data",
        lambda: pd.DataFrame(
            [
                {"流水号": "SN001", "状态": "已出库", "更新时间": ""},
            ]
        ),
    )
    monkeypatch.setattr(inventory_route, "save_data", lambda df: None)
    monkeypatch.setattr(inventory_route, "archive_shipped_data", lambda df: None)
    monkeypatch.setattr(inventory_route, "append_log", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException, match="已出库"):
        confirm_shipping(
            ShippingActionPayload(serial_nos=["SN001"]),
            request=MagicMock(spec=Request),
            current_operator="tester",
            current_user={"username": "tester"}
        )
