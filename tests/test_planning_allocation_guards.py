import pandas as pd
import pytest
from fastapi import HTTPException

from api.routes.planning import (
    OrderAllocatePayload,
    OrderReleasePayload,
    allocate_order_inventory_api,
    release_order_inventory_api,
)


def test_allocate_order_inventory_rejects_empty_selection():
    with pytest.raises(HTTPException) as exc:
        allocate_order_inventory_api("SO-001", OrderAllocatePayload(selected_serial_nos=[]), current_operator="tester")

    assert exc.value.status_code == 422
    assert "请先选择要配货的机台" in str(exc.value.detail)


def test_release_order_inventory_rejects_non_matching_selection(monkeypatch):
    import api.routes.planning as planning_route

    monkeypatch.setattr(
        planning_route,
        "get_data",
        lambda: pd.DataFrame(
            [
                {"流水号": "SN001", "占用订单号": "SO-001", "状态": "待发货"},
                {"流水号": "SN002", "占用订单号": "SO-002", "状态": "待发货"},
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        release_order_inventory_api(
            "SO-001",
            OrderReleasePayload(all=False, selected_serial_nos=["SN002"]),
            current_operator="tester",
        )

    assert exc.value.status_code == 422
    assert "所选机台不属于当前订单或已不可释放" in str(exc.value.detail)


def test_allocate_order_inventory_marks_machine_as_pending_shipping(monkeypatch):
    import api.routes.planning as planning_route

    calls = {}
    monkeypatch.setattr(
        planning_route,
        "get_orders",
        lambda: pd.DataFrame(
            [
                {"订单号": "SO-001", "客户名": "客户A", "代理商": "代理A", "备注": "加急"},
            ]
        ),
    )
    monkeypatch.setattr(
        planning_route,
        "allocate_inventory",
        lambda order_id, customer, agent, selected, operator=None: calls.update(
            {
                "order_id": order_id,
                "customer": customer,
                "agent": agent,
                "selected": selected,
                "operator": operator,
            }
        ),
    )

    result = allocate_order_inventory_api(
        "SO-001",
        OrderAllocatePayload(selected_serial_nos=["SN001", "SN002"]),
        current_operator="tester",
    )

    assert result["message"] == "配货成功，已锁定 2 台机台"
    assert calls == {
        "order_id": "SO-001",
        "customer": "客户A",
        "agent": "代理A",
        "selected": ["SN001", "SN002"],
        "operator": "tester",
    }


def test_release_order_inventory_all_reverts_to_pending_inbound(monkeypatch):
    import api.routes.planning as planning_route

    reverted = {}
    monkeypatch.setattr(
        planning_route,
        "get_data",
        lambda: pd.DataFrame(
            [
                {"流水号": "SN001", "占用订单号": "SO-001", "状态": "待发货"},
                {"流水号": "SN002", "占用订单号": "SO-001", "状态": "待发货"},
                {"流水号": "SN003", "占用订单号": "SO-002", "状态": "待发货"},
            ]
        ),
    )
    monkeypatch.setattr(
        planning_route,
        "revert_to_inbound",
        lambda sns, reason="", operator=None: reverted.update(
            {"sns": sns, "reason": reason, "operator": operator}
        ),
    )

    result = release_order_inventory_api(
        "SO-001",
        OrderReleasePayload(all=True, selected_serial_nos=[]),
        current_operator="tester",
    )

    assert result == {"message": "已释放 2 台机台", "released": 2}
    assert reverted == {
        "sns": ["SN001", "SN002"],
        "reason": "订单配货释放-SO-001",
        "operator": "tester",
    }


@pytest.mark.xfail(reason="当前配货接口尚未限制所选机台数量不能超过订单需求数量")
def test_allocate_order_inventory_rejects_over_order_quantity(monkeypatch):
    import api.routes.planning as planning_route

    monkeypatch.setattr(
        planning_route,
        "get_orders",
        lambda: pd.DataFrame(
            [
                {"订单号": "SO-001", "客户名": "客户A", "代理商": "代理A", "备注": "", "需求数量": 1},
            ]
        ),
    )

    with pytest.raises(HTTPException, match="需求数量"):
        allocate_order_inventory_api(
            "SO-001",
            OrderAllocatePayload(selected_serial_nos=["SN001", "SN002"]),
            current_operator="tester",
        )
