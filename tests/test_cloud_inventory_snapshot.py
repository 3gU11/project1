from pathlib import Path

from sqlalchemy import create_engine, text

import crud.cloud_dealer_order_sync as sync


def test_bridge_stock_predicate_includes_location_suffixed_inventory():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE finished_goods_data (`状态` TEXT)"))
        connection.execute(
            text("INSERT INTO finished_goods_data VALUES (:status)"),
            [
                {"status": "库存中"},
                {"status": "库存中（DG-WH）"},
                {"status": "库存中（A01）"},
                {"status": "待入库"},
                {"status": "已出库"},
            ],
        )
        predicate = getattr(
            sync,
            "BRIDGE_STOCK_STATUS_PREDICATE",
            "TRIM(COALESCE(`状态`, '')) = '库存中'",
        )
        count = connection.execute(
            text(
                "SELECT COUNT(*) FROM finished_goods_data "
                f"WHERE {predicate}"
            )
        ).scalar_one()

    assert count == 3


def test_full_and_incremental_mysql_refresh_use_the_same_stock_prefix():
    sql = Path(__file__).parents[1].joinpath("scripts", "wechat_batch_summary.sql").read_text(encoding="utf-8")
    expected = "TRIM(COALESCE(`状态`, '')) LIKE '库存中%'"
    stock_marker = "'库存中' AS `batch_no`"
    assert sql.count(expected) >= 2
    assert "TRIM(COALESCE(`状态`, '')) = '库存中'" not in sql
    assert sql.count(stock_marker) >= 2


def test_python_fallback_marks_heightened_finished_units_as_stock():
    source = Path(__file__).parents[1].joinpath("crud", "cloud_dealer_order_sync.py").read_text(encoding="utf-8")

    assert "'库存中' AS batch_no" in source


def test_inventory_models_must_match_enabled_model_dictionary():
    sql = Path(__file__).parents[1].joinpath("scripts", "wechat_batch_summary.sql").read_text(encoding="utf-8")
    source = Path(__file__).parents[1].joinpath("crud", "cloud_dealer_order_sync.py").read_text(encoding="utf-8")

    # 机型严格按启用中的机型字典过滤：SQL 4 处子查询 + Python 兜底 2 处刷新 + 1 处告警审计
    assert sql.count("INNER JOIN (") >= 4
    assert sql.count("SELECT DISTINCT TRIM(`model_name`) AS `model_name`") >= 4
    assert source.count("SELECT DISTINCT TRIM(model_name) AS model_name") >= 3
    # 不再用 REPLACE 清洗机型，基础机型就是字典里的原值
    assert "REPLACE(REPLACE(TRIM(`机型`)" not in sql
    assert "REPLACE(REPLACE(TRIM(`机型`)" not in source
    assert "TRIM(`机型`) AS `base_model`" in sql
    assert "TRIM(`机型`) AS base_model" in source


def test_heightened_only_recognized_from_remark_and_legacy_batch_marker():
    sql = Path(__file__).parents[1].joinpath("scripts", "wechat_batch_summary.sql").read_text(encoding="utf-8")
    source = Path(__file__).parents[1].joinpath("crud", "cloud_dealer_order_sync.py").read_text(encoding="utf-8")

    for text in (sql, source):
        assert "TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'" in text
        assert "LIKE '%附加%'" in text
        # 不从机型名判断加高（加高只出现在备注里，机型必须是字典值）
        assert "TRIM(COALESCE(`机型`, '')) LIKE '%加高%'" not in text
    assert "OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'" in source


def test_unknown_model_rows_are_skipped_and_logged():
    source = Path(__file__).parents[1].joinpath("crud", "cloud_dealer_order_sync.py").read_text(encoding="utf-8")

    assert "md.model_name IS NULL" in source
    assert "skipped_unknown_models" in source
    assert "机型不在启用中的机型字典里" in source
    assert "请让工厂修正机型/字典" in source
    assert "DELETE w FROM wechat_batch_summary w" in source

