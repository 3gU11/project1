import pytest
import pandas as pd
from fastapi import HTTPException

from api.routes.planning import SalesOrderCreatePayload, create_sales_order_api, _link_contracts_to_order


def test_create_sales_order_preserves_http_exception(monkeypatch):
    import api.routes.planning as planning_route

    def raise_invalid_model(_models):
        raise HTTPException(status_code=422, detail="机型不在字典中或未启用: BAD-MODEL")

    monkeypatch.setattr(planning_route, "_assert_models_in_dictionary", raise_invalid_model)

    payload = SalesOrderCreatePayload(
        客户名="测试客户",
        代理商="测试代理",
        需求机型="BAD-MODELx2",
        需求数量=2,
        备注="合并订单",
        包装选项="需要包装",
        发货时间="2026-04-27",
    )

    with pytest.raises(HTTPException) as exc:
        create_sales_order_api(
            payload,
            request=None,
            current_operator="tester",
            current_user={"username": "tester"},
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "机型不在字典中或未启用: BAD-MODEL"


def test_link_contracts_to_order_marks_all_contract_rows_converted(monkeypatch):
    import api.routes.planning as planning_route
    from unittest.mock import MagicMock

    mock_conn = MagicMock()
    
    mock_result_existing = MagicMock()
    mock_result_existing.fetchall.return_value = []
    
    mock_result_update = MagicMock()
    mock_result_update.rowcount = 2
    
    mock_conn.execute.side_effect = [mock_result_existing, mock_result_update]
    
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_engine.begin.return_value.__exit__ = lambda self, *args: None
    
    monkeypatch.setattr(planning_route, "get_engine", lambda: mock_engine)
    monkeypatch.setattr(planning_route, "_sync_order_to_units_and_import", lambda contract_ids, order_id: {})
    monkeypatch.setattr(planning_route, "_occupy_inventory_for_order", lambda contract_ids, order_id: 0)

    linked = _link_contracts_to_order(["C-001"], "SO-TEST")

    assert linked == 2
    
    call_args_list = mock_conn.execute.call_args_list
    assert len(call_args_list) == 2
    
    select_call = call_args_list[0]
    select_params = select_call[0][1]
    assert select_params["cids"] == ["C-001"]
    assert select_params["oid"] == "SO-TEST"
    
    update_call = call_args_list[1]
    update_params = update_call[0][1]
    assert update_params["cids"] == ["C-001"]
    assert update_params["oid"] == "SO-TEST"
    assert update_params["status"] == "已转订单"
