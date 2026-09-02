import pandas as pd

from crud.reports import (
    build_model_report_appendices,
    get_dealer_sales_summary,
    get_order_model_quantities,
    serialize_model_report_appendices,
)


def _dictionary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"model_name": "FR-400XS(PRO)", "model_family": "中小型XS", "sort_order": 1},
            {"model_name": "FR-400AUTO", "model_family": "中小型AUTO", "sort_order": 2},
            {"model_name": "FR-400G", "model_family": "中小型G", "sort_order": 3},
            {"model_name": "FR-1100XS(PRO)", "model_family": "特殊", "sort_order": 4},
        ]
    )


def test_appendices_keep_unmatched_out_of_screw_reference():
    quantities = pd.DataFrame(
        [
            {"机型": "FR-400XS(PRO)", "数量": 10},
            {"机型": "FR-400AUTO", "数量": 5},
            {"机型": "FR-400G", "数量": 3},
            {"机型": "FR-1100XS(PRO)", "数量": 1},
            {"机型": "FR-999", "数量": 1},
        ]
    )

    appendices = build_model_report_appendices(quantities, _dictionary())

    family = appendices["总族类比例"]
    assert family.iloc[-1].to_dict() == {
        "总族类": "全部总族类",
        "累计出货": 20,
        "总族类比例": "100.00%",
        "机型数": 5,
    }
    assert family.loc[family["总族类"] == "特殊", "累计出货"].iloc[0] == 1
    assert family.loc[family["总族类"] == "未匹配", "累计出货"].iloc[0] == 1

    screw = appendices["丝杆订货需求比例"]
    assert screw.iloc[-1].tolist() == ["XS 合计", 10, "100.00%", "AUTO 合计", 5, "100.00%", "G 合计", 3, "100.00%"]
    preview_screw = serialize_model_report_appendices(appendices)["丝杆订货需求比例"]
    assert preview_screw[-1] == {
        "xs_name": "XS 合计",
        "xs_quantity": 10,
        "xs_ratio": "100.00%",
        "auto_name": "AUTO 合计",
        "auto_quantity": 5,
        "auto_ratio": "100.00%",
        "g_name": "G 合计",
        "g_quantity": 3,
        "g_ratio": "100.00%",
    }


def test_order_agent_summary_uses_order_total_and_keeps_blank_dealer():
    orders = pd.DataFrame(
        [
            {"需求机型": "FR-400XS(PRO) x 2; FR-400AUTO x 3", "需求数量": 5, "代理商": "甲"},
            {"需求机型": "FR-400G x 4", "需求数量": 4, "代理商": ""},
        ]
    )

    quantities = get_order_model_quantities(orders)
    assert quantities.to_dict("records") == [
        {"机型": "FR-400XS(PRO)", "数量": 2},
        {"机型": "FR-400AUTO", "数量": 3},
        {"机型": "FR-400G", "数量": 4},
    ]

    dealers = get_dealer_sales_summary(orders)
    assert dealers.to_dict("records") == [
        {"代理商": "甲", "所售数量": 5, "总销售占比": "55.56%"},
        {"代理商": "未填写", "所售数量": 4, "总销售占比": "44.44%"},
        {"代理商": "合计", "所售数量": 9, "总销售占比": "100.00%"},
    ]
