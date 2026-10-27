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


def test_special_heightened_height_uses_default_height_rule():
    sync = __import__("crud.cloud_dealer_order_sync", fromlist=["x"])

    # 默认高度：FR-400G = 100mm，其余机型 = 200mm
    assert not sync.is_special_heightened("FR-8060XS(PRO)", "加高200mm")
    assert not sync.is_special_heightened("FR-400G", "加高100mm")
    assert not sync.is_special_heightened(" fr-400g ", "加高100mm")
    assert not sync.is_special_heightened("FR-400G", "加高")
    assert not sync.is_special_heightened("FR-8060XS(PRO)", "加高")
    assert not sync.is_special_heightened("FR-8060XS(PRO)", "打样（加高）")

    # 非默认高度：特殊加高只能走合同预订，不能作为可选购库存
    assert sync.is_special_heightened(
        "FR-8060XS(PRO)",
        "加高400mm，四轴三菱，后号电，配旋转头NRT-C300H,三菱变频器(PRO)(齐齐哈尔)",
    )
    assert sync.is_special_heightened("FR-8060XS(PRO)", "加高100mm总线")
    assert sync.is_special_heightened("FR-400G", "加高200mm")
    assert sync.is_special_heightened("FR-8060XS(PRO)", "加高 加高至500MM")
    assert sync.is_special_heightened("FR-8060XS(PRO)", "Z轴加高至650")
    # “加高4轴”是配置描述，不是高度
    assert not sync.is_special_heightened("FR-8060XS(PRO)", "加高4轴")


def test_special_heightened_units_are_stripped_from_cloud_snapshot_rows():
    sync = __import__("crud.cloud_dealer_order_sync", fromlist=["x"])
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE finished_goods_data ("
                "`批次号` TEXT, `机型` TEXT, `状态` TEXT, `预计入库时间` TEXT, `合同备注` TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO finished_goods_data "
                "(`批次号`, `机型`, `状态`, `预计入库时间`, `合同备注`) VALUES "
                "(:batch, :model, :status, :eta, :remark)"
            ),
            [
                # 8060XS 加高400mm / 加高100mm：非默认 200mm，必须排除
                {"batch": "08-13", "model": "FR-8060XS(PRO)", "status": "待入库",
                 "eta": "2026-10-15 00:00:00", "remark": "加高400mm，四轴三菱，后号电"},
                {"batch": "09-14", "model": "FR-8060XS(PRO)", "status": "待入库",
                 "eta": "2026-10-31 00:00:00", "remark": "加高100mm总线"},
                # 默认 200mm，保留
                {"batch": "09-11", "model": "FR-8060XS(PRO)", "status": "待入库",
                 "eta": "2026-10-24 00:00:00", "remark": "加高200mm"},
                # FR-400G 默认 100mm，保留
                {"batch": "09-16", "model": "FR-400G", "status": "待入库",
                 "eta": "2026-10-31 00:00:00", "remark": "加高100mm"},
                # 同一批次既有默认又有特殊：只扣减特殊台数
                {"batch": "09-20", "model": "FR-8060XS(PRO)", "status": "待入库",
                 "eta": "2026-11-01 00:00:00", "remark": "加高200mm"},
                {"batch": "09-20", "model": "FR-8060XS(PRO)", "status": "待入库",
                 "eta": "2026-11-01 00:00:00", "remark": "加高400mm"},
                # 库存中：默认 200mm 保留；加高至500MM 排除
                {"batch": "07-20", "model": "FR-400XS(PRO)", "status": "库存中（E03）",
                 "eta": None, "remark": "加高200mm"},
                {"batch": "04-09", "model": "FR-8055XS(PRO)", "status": "库存中（待发货缓冲区02）",
                 "eta": None, "remark": "加高 加高至500MM"},
            ],
        )
        rows = [
            {"summary_id": "s1", "batch_no": "加高", "expected_inbound_time": "2026-10-15 00:00:00",
             "model": "FR-8060XS(PRO)", "quantity": 1, "heightened": 1,
             "original_batch_no": "08-13", "original_expected_inbound_time": "2026-10-15 00:00:00"},
            {"summary_id": "s2", "batch_no": "加高", "expected_inbound_time": "2026-10-31 00:00:00",
             "model": "FR-8060XS(PRO)", "quantity": 1, "heightened": 1,
             "original_batch_no": "09-14", "original_expected_inbound_time": "2026-10-31 00:00:00"},
            {"summary_id": "s3", "batch_no": "加高", "expected_inbound_time": "2026-10-24 00:00:00",
             "model": "FR-8060XS(PRO)", "quantity": 1, "heightened": 1,
             "original_batch_no": "09-11", "original_expected_inbound_time": "2026-10-24 00:00:00"},
            {"summary_id": "s4", "batch_no": "加高", "expected_inbound_time": "2026-10-31 00:00:00",
             "model": "FR-400G", "quantity": 1, "heightened": 1,
             "original_batch_no": "09-16", "original_expected_inbound_time": "2026-10-31 00:00:00"},
            {"summary_id": "s5", "batch_no": "加高", "expected_inbound_time": "2026-11-01 00:00:00",
             "model": "FR-8060XS(PRO)", "quantity": 2, "heightened": 1,
             "original_batch_no": "09-20", "original_expected_inbound_time": "2026-11-01 00:00:00"},
            {"summary_id": "s6", "batch_no": "库存中", "expected_inbound_time": None,
             "model": "FR-400XS(PRO)", "quantity": 1, "heightened": 1,
             "original_batch_no": "07-20", "original_expected_inbound_time": None},
            {"summary_id": "s7", "batch_no": "库存中", "expected_inbound_time": None,
             "model": "FR-8055XS(PRO)", "quantity": 1, "heightened": 1,
             "original_batch_no": "04-09", "original_expected_inbound_time": None},
            {"summary_id": "s8", "batch_no": "09-11", "expected_inbound_time": "2026-10-24 00:00:00",
             "model": "FR-500G", "quantity": 1, "heightened": 0,
             "original_batch_no": "", "original_expected_inbound_time": None},
        ]

        kept, excluded = sync.strip_special_heightened_rows(connection, rows)

    by_id = {row["summary_id"]: row for row in kept}
    assert excluded == 4
    assert "s1" not in by_id
    assert "s2" not in by_id
    assert "s7" not in by_id
    # 同一批次混合高度：只保留默认 200mm 的 1 台
    assert by_id["s5"]["quantity"] == 1
    assert by_id["s3"]["quantity"] == 1
    assert by_id["s4"]["quantity"] == 1
    assert by_id["s6"]["quantity"] == 1
    assert by_id["s8"]["quantity"] == 1

