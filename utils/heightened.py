"""加高判定（统一口径）。

同一段备注在不同位置会被用来推断「加高」，但备注里既有转合同追加的独立标记，也有
说明文字：经销商订单的订单备注（如「400G加高100mm 配单滤水箱」）会被云端复制到每一行，
转合同时再逐行写进合同备注。只看「加高」两个字会把整单所有机型都误判成加高。

所以加高只认三种信号：
  1. 机型名自带「(加高)」/「（加高）」；
  2. 转合同时单独追加的「加高」标记（前后是空格，例如「… 加高 [备注]…」）；
  3. 不在说明分段里的纯文本备注（历史数据，如「加高500MM」）。

说明分段指备注里的「[总]整单备注」「[备注]原备注」「[附加]附加备注」「[改数]改数量」。

另外约定：机型字段必须严格对齐机型字典——字典里只有基础机型，「加高」是机台的规格属性，
统一用备注/加高标记表达。展示、统计、写库前一律用 split_heightened_model_name 把历史数据
里拼在机型后面的「(加高)」剥掉，避免同一机型拆成两行。
"""
from __future__ import annotations

import re

# 备注里的方括号分段：[总]整单备注、[备注]原备注、[附加]附加备注、[改数]需要修改数量。
# 只匹配这些已知分段，未知方括号内容保持原样，避免误伤历史备注。
_NOTE_SEGMENT_RE = re.compile(r"\[(?:总|备注|附加|改数)\][^\[]*")
# 转合同时在 [总] 备注后单独追加的「加高」标记（前后有空格），与备注正文区分开。
_HIGH_MARKER_TOKEN_RE = re.compile(r"(?<!\S)加高(?!\S)")
# 机型名后缀「(加高)」「（加高）」：历史数据/外部系统会把规格拼进机型，必须剥掉。
_HEIGHTENED_NAME_SUFFIX_RE = re.compile(r"\s*[（(]\s*加高\s*[）)]\s*")


def split_heightened_model_name(model: object) -> tuple[str, bool]:
    """把「FR-400G(加高)」拆成机型字典里的「FR-400G」和加高标记。

    返回 (机型字典机型, 是否加高)；没有加高后缀时原样返回（只去首尾空白）。
    """
    raw = str(model or "").strip()
    base = _HEIGHTENED_NAME_SUFFIX_RE.sub("", raw).strip()
    return base, bool(base and base != raw)


def normalize_dictionary_model_name(model: object) -> str:
    """机型统一成机型字典里的基础机型（去掉拼在后面的「(加高)」）。"""
    return split_heightened_model_name(model)[0]


def is_high_text_hint(*values: object) -> bool:
    """判断机型/备注等文本里有没有加高信号；说明分段里的「加高」不算。"""
    for value in values:
        text = str(value or "")
        if "加高" in _NOTE_SEGMENT_RE.sub(" ", text):
            return True
        if _HIGH_MARKER_TOKEN_RE.search(text):
            return True
    return False
