"""云端经销商订单同步：多明细订单的行级备注不得继承首行/订单级汇总值。

云端 8003 桥接按首行明细 Object.assign 生成订单级 remark/extraRemark，多行订单里
订单级备注实际等于首行明细值；同步到本地 dealer_orders 时若按行回退订单级字段，
会把首行备注写进其它明细行。只有单明细（或旧接口无明细）订单才允许订单级兜底。
"""

import crud.cloud_dealer_order_sync as sync


def _payloads(order: dict) -> list[dict]:
    return [sync._line_payload(item, order) for item in sync._iter_cloud_items(order)]


def test_multi_line_order_notes_not_inherited_from_first_line():
    order = {
        "order_no": "DO17942853598375658F9",
        "remark": "首行原备注",
        "extra_remark": "配:3mm导管·适用数量1",
        "items": [
            {
                "line_no": 10019,
                "model": "FH-300C",
                "quantity": 1,
                "remark": "首行原备注",
                "extra_remark": "配:3mm导管·适用数量1",
                "ERMQ": 1,
            },
            {"line_no": 10020, "model": "FR-400G", "quantity": 2},
            {"line_no": 10021, "model": "FR-400AUTO", "quantity": 1},
        ],
    }

    payloads = _payloads(order)

    assert payloads[0]["remark"] == "首行原备注"
    assert payloads[0]["extra_remark"] == "配:3mm导管·适用数量1"
    assert payloads[0]["ERMQ"] == 1
    for payload in payloads[1:]:
        assert payload["remark"] == ""
        assert payload["extra_remark"] == ""
        # 附加备注为空时不得凭空把数量写成需改数量
        assert payload["ERMQ"] == 0


def test_multi_line_order_keeps_third_line_own_notes():
    order = {
        "order_no": "DO-MULTI-THIRD-LINE",
        "remark": "首行原备注",
        "extra_remark": "首行附加备注",
        "items": [
            {
                "line_no": 1,
                "model": "FH-300C",
                "quantity": 1,
                "remark": "首行原备注",
                "extra_remark": "首行附加备注",
            },
            {"line_no": 2, "model": "FR-400G", "quantity": 2},
            {
                "line_no": 3,
                "model": "FR-400AUTO",
                "quantity": 1,
                "remark": "第三行原备注",
                "extra_remark": "配:3mm导管·适用数量1",
                "ERMQ": 1,
            },
        ],
    }

    payloads = _payloads(order)

    assert payloads[1]["remark"] == ""
    assert payloads[1]["extra_remark"] == ""
    assert payloads[2]["remark"] == "第三行原备注"
    assert payloads[2]["extra_remark"] == "配:3mm导管·适用数量1"
    assert payloads[2]["ERMQ"] == 1


def test_single_line_order_keeps_order_level_fallback():
    order = {
        "order_no": "DO-SINGLE-LINE",
        "remark": "订单级原备注",
        "extra_remark": "订单级附加备注",
        "items": [{"line_no": 1, "model": "FR-400G", "quantity": 2}],
    }

    payload = _payloads(order)[0]

    assert payload["remark"] == "订单级原备注"
    assert payload["extra_remark"] == "订单级附加备注"


def test_order_without_items_keeps_order_level_notes():
    order = {
        "order_no": "DO-NO-ITEMS",
        "model": "FR-400G",
        "quantity": 1,
        "remark": "订单级原备注",
        "extra_remark": "订单级附加备注",
    }

    payload = _payloads(order)[0]

    assert payload["remark"] == "订单级原备注"
    assert payload["extra_remark"] == "订单级附加备注"
