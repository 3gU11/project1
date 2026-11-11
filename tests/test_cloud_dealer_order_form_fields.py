"""桥接订单表单字段 → V8 dealer_orders 行字段的最小回归测试。

背景：V8「经销商订单审核」读取的地址/办事处/经销商电话来自云端桥接
`/api/v8/bridge/orders`；桥接 SELECT 漏字段时 V8 收到空值，页面显示为「-」。
"""

from crud.cloud_dealer_order_sync import _line_payload


def test_bridge_form_fields_are_mapped_to_review_columns():
    payload = _line_payload(
        {
            "orderNo": "ADDR-TEST-001",
            "lineNo": 1,
            "dealerName": "地址测试经销商",
            "dealerPhone": "13800138000",
            "customerName": "地址测试客户",
            "deliveryAddress": "浙江省宁波市测试路88号 3幢 201室",
            "officeName": "宁波办事处",
            "officeContact": "李四",
            "officePhone": "13900000000",
            "contactName": "张三",
            "contactPhone": "13800138000",
            "model": "FR-400G",
            "quantity": 1,
            "deliveryDate": "2026-11-25",
        },
        {"orderNo": "ADDR-TEST-001"},
    )

    assert payload["delivery_address"] == "浙江省宁波市测试路88号 3幢 201室"
    assert payload["office_name"] == "宁波办事处"
    assert payload["office_contact"] == "李四"
    assert payload["office_phone"] == "13900000000"
    assert payload["dealer_phone"] == "13800138000"
    assert payload["delivery_date"] == "2026-11-25"
