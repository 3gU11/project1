"""转合同兜底明细的加高判定：只认明细自己的 inventory_type / 机型，不认被复制的订单备注。

现场问题：订单备注「400G加高100mm 配单滤水箱 加装割铝装置」被云端复制到每一行明细，
转合同弹窗按备注判断加高，导致 4 个机型全部被勾选加高，实际只有 FR-400G 一台加高。
"""
from api.routes import dealer_orders

SHARED_REMARK = "400G加高100mm 配单滤水箱 加装割铝装置"


def _line(model: str, inventory_type: str = "finished", remark: str = SHARED_REMARK) -> dict:
    return {"model": model, "quantity": 1, "inventory_type": inventory_type, "remark": remark}


def test_shared_order_remark_does_not_mark_every_line_heightened():
    items = [
        _line("FH-300C"),
        _line("FR-400G", "heightened"),
        _line("FR-400AUTO"),
        _line("FR-500XS(PRO)"),
    ]

    assert [dealer_orders._line_is_heightened(item) for item in items] == [False, True, False, False]


def test_heightened_line_detected_by_inventory_type_or_model_name():
    assert dealer_orders._line_is_heightened({"model": "FR-400G", "inventory_type": "Heightened"}) is True
    assert dealer_orders._line_is_heightened({"model": "FR-400G(加高)"}) is True
    # 只有订单备注出现「加高」不算
    assert dealer_orders._line_is_heightened(_line("FR-400G")) is False
