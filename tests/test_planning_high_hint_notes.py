"""加高判定不能把备注说明文字（[总]/[备注]/[附加] 分段）当成加高信号。

现场问题：经销商订单备注「400G加高100mm 配单滤水箱 加装割铝装置」被云端复制到每一行，
转合同时这段备注又逐行写进合同备注，原来的「备注包含加高即加高」判断会把整单所有机型
都当成加高。加高只认机型名里的「(加高)」或转合同单独追加的「加高」标记。
"""
import pandas as pd

from api.routes import planning

SHARED_NOTE = (
    "[总]400G加高100mm 配单滤水箱 加装割铝装置 "
    "[备注]400G加高100mm 配单滤水箱 加装割铝装置 [改数]0"
)
HIGH_NOTE = (
    "[总]400G加高100mm 配单滤水箱 加装割铝装置 加高 "
    "[备注]400G加高100mm 配单滤水箱 加装割铝装置 [改数]0"
)


def test_note_paragraphs_do_not_mark_row_high():
    assert planning._is_high_model_hint("FH-300C", SHARED_NOTE) is False
    assert planning._is_high_model_hint("FR-400AUTO", SHARED_NOTE) is False


def test_explicit_marker_or_model_suffix_marks_high():
    assert planning._is_high_model_hint("FR-400G", HIGH_NOTE) is True
    assert planning._is_high_model_hint("FR-400G(加高)") is True
    assert planning._is_high_model_hint("FR-400G（加高）") is True


def test_plain_heightened_note_keeps_working():
    """不在方括号分段里的纯文本备注（老数据）仍然按加高处理。"""
    assert planning._is_high_model_hint("FH-300C", "加高100mm") is True
    assert planning._is_high_model_hint("FH-300C", "批次 加高") is True


def test_inventory_row_with_contract_note_segments_is_not_high():
    normal_row = pd.Series({"机型": "FH-300C", "批次号": "FINISHED-STOCK", "合同备注": SHARED_NOTE})
    high_row = pd.Series({"机型": "FR-400G", "批次号": "08-04", "合同备注": HIGH_NOTE})

    assert planning._inventory_row_high(normal_row) is False
    assert planning._inventory_row_high(high_row) is True
    # 普通机台只能满足普通需求，加高需求只认真正的加高机台
    assert planning._machine_matches_model_requirement(normal_row, "FH-300C", False) is True
    assert planning._machine_matches_model_requirement(normal_row, "FH-300C", True) is False
