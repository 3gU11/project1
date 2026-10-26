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
