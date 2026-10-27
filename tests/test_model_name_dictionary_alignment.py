"""机型字段严格对齐机型字典：历史/外部数据拼在机型后面的「(加高)」要剥掉，

加高信息保留在备注里，保证同一机型在排产、统计、订单里不会拆成两行。
"""
import pandas as pd

from crud.planning import align_factory_plan_models
from utils.heightened import normalize_dictionary_model_name, split_heightened_model_name


def test_split_heightened_model_name():
    assert split_heightened_model_name("FR-400G(加高)") == ("FR-400G", True)
    assert split_heightened_model_name("FR-400G（加高）") == ("FR-400G", True)
    assert split_heightened_model_name(" FR-400G（ 加高 ） ") == ("FR-400G", True)
    assert split_heightened_model_name("FR-400G") == ("FR-400G", False)
    assert split_heightened_model_name(None) == ("", False)


def test_normalize_dictionary_model_name():
    assert normalize_dictionary_model_name("FR-500XS(PRO)(加高)") == "FR-500XS(PRO)"
    assert normalize_dictionary_model_name("FR-500XS(PRO)") == "FR-500XS(PRO)"


def test_align_factory_plan_models_strips_suffix_and_keeps_high_flag():
    df = pd.DataFrame([
        {"合同号": "HT1", "机型": "FR-400G(加高)", "排产数量": 1, "备注": ""},
        {"合同号": "HT1", "机型": "FR-500XS(PRO)", "排产数量": 2, "备注": "普通备注"},
        {"合同号": "HT2", "机型": "FR-600G(加高)", "排产数量": 1, "备注": "加高500MM"},
    ])

    out = align_factory_plan_models(df)

    assert out["机型"].tolist() == ["FR-400G", "FR-500XS(PRO)", "FR-600G"]
    assert "加高" in out.loc[0, "备注"]
    assert "加高" not in out.loc[1, "备注"]
    # 备注里已有加高描述时不重复追加
    assert out.loc[2, "备注"] == "加高500MM"
