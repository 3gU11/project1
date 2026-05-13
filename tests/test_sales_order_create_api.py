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

    plan_df = pd.DataFrame(
        [
            {"合同号": "C-001", "机型": "FR-100", "排产数量": 1, "状态": "已规划", "订单号": ""},
            {"合同号": "C-001", "机型": "FR-200", "排产数量": 1, "状态": "已规划", "订单号": ""},
            {"合同号": "C-002", "机型": "FR-300", "排产数量": 1, "状态": "已规划", "订单号": ""},
        ]
    )
    saved = {}

    monkeypatch.setattr(planning_route, "get_factory_plan", lambda: plan_df.copy())
    monkeypatch.setattr(planning_route, "save_factory_plan", lambda df: saved.setdefault("df", df.copy()))
    monkeypatch.setattr(planning_route, "_sync_order_to_units_and_import", lambda contract_ids, order_id: {})
    monkeypatch.setattr(planning_route, "_occupy_inventory_for_order", lambda contract_ids, order_id: 0)

    linked = _link_contracts_to_order(["C-001"], "SO-TEST")

    assert linked == 2
    linked_rows = saved["df"][saved["df"]["合同号"] == "C-001"]
    assert linked_rows["订单号"].tolist() == ["SO-TEST", "SO-TEST"]
    assert linked_rows["状态"].tolist() == ["已转订单", "已转订单"]
    untouched = saved["df"][saved["df"]["合同号"] == "C-002"].iloc[0]
    assert untouched["订单号"] == ""
    assert untouched["状态"] == "已规划"
