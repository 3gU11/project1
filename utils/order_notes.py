"""订单/合同行备注 → 机台「单行备注」口径。

转合同时一行备注可能是多段拼接：

    [总]整单备注 加高 [备注]原备注 [附加]附加备注 [改数]2

机台（finished_goods_data.合同备注 / units.order_remark）只保留一行备注，
业务人员在「订单配货」里据此手动判别分配。取值优先级：

1. [备注] 原备注
2. [附加] 附加备注
3. 加高标记 / [改数] 改数量

两个输出口径：

- ``single_line_order_remark``：给人看的纯文本（展示/接口字段）；
- ``machine_remark_text``：落到机台的单行备注。原备注/附加备注保留 ``[备注]``/``[附加]``
  分段，避免备注正文里的「加高」说明被后续加高判定误当成加高信号（历史问题见
  ``utils/heightened.py`` 的文件说明）；「加高」「改数」本身是语义标记，按纯文本落库。

整单备注 [总] 不属于单行备注；换行、制表符和连续空白统一压成单个空格。
"""

from __future__ import annotations

import re

# 备注里的方括号分段；只认已知分段，未知方括号保持原样。
_SEGMENT_RE = re.compile(r"\[(总|备注|附加|改数)\]([^\[]*)")
# 转合同时单独追加的「加高」标记（前后是空格），与备注正文区分开。
_HIGH_MARKER_RE = re.compile(r"(?:^|\s)加高(?=\s|$)")


def _single_line(value: object) -> str:
    return " ".join(str(value or "").split())


def _segments(raw: str) -> dict[str, str]:
    segments: dict[str, str] = {}
    for match in _SEGMENT_RE.finditer(raw):
        key = match.group(1)
        content = _single_line(match.group(2))
        if content and key not in segments:
            segments[key] = content
    return segments


def _markers(raw: str, segments: dict[str, str]) -> list[str]:
    markers: list[str] = []
    # 与 utils.heightened 的加高口径一致：转合同追加的「加高」是独立标记（前后空格）。
    if _HIGH_MARKER_RE.search(raw):
        markers.append("加高")
    change_qty = segments.get("改数", "")
    if change_qty.isdigit() and int(change_qty) > 0:
        markers.append(f"改数{change_qty}")
    return markers


def single_line_order_remark(value: object) -> str:
    """从合同/订单行备注里提取一行纯文本备注；没有任何有效内容时返回空串。"""
    raw = _single_line(value)
    if not raw:
        return ""

    segments = _segments(raw)
    for key in ("备注", "附加"):
        if segments.get(key):
            return segments[key]

    markers = _markers(raw, segments)
    if markers:
        return " ".join(markers)

    # 历史/外部数据没有分段：去掉 [总] 等分段后保留原文（整单备注不属于单行备注）。
    return _single_line(_SEGMENT_RE.sub(" ", raw))


def machine_remark_text(value: object) -> str:
    """落到机台的单行备注：原备注/附加备注保留分段标记，避免正文「加高」误判。"""
    raw = _single_line(value)
    if not raw:
        return ""

    segments = _segments(raw)
    for key in ("备注", "附加"):
        if segments.get(key):
            return f"[{key}]{segments[key]}"

    markers = _markers(raw, segments)
    if markers:
        return " ".join(markers)

    return _single_line(_SEGMENT_RE.sub(" ", raw))
