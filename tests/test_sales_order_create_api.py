import pytest
from fastapi import HTTPException

from api.routes.planning import SalesOrderCreatePayload, create_sales_order_api


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
