import pandas as pd
from sqlalchemy import create_engine, text

from crud import inventory as inventory_crud


def _build_engine_with_plan_import(include_status):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        if include_status:
            conn.execute(text(
                "CREATE TABLE plan_import ("
                "流水号 TEXT PRIMARY KEY, 批次号 TEXT, 机型 TEXT, 状态 TEXT NOT NULL DEFAULT '待入库', "
                "预计入库时间 TEXT, `客户` TEXT, `代理商` TEXT, `合同备注` TEXT, `合同号` TEXT)"
            ))
        else:
            conn.execute(text(
                "CREATE TABLE plan_import ("
                "流水号 TEXT PRIMARY KEY, 批次号 TEXT, 机型 TEXT, "
                "预计入库时间 TEXT, `客户` TEXT, `代理商` TEXT, `合同备注` TEXT, `合同号` TEXT)"
            ))
    return engine


def test_append_import_staging_auto_add_status_column(monkeypatch):
    engine = _build_engine_with_plan_import(include_status=False)
    monkeypatch.setattr(inventory_crud, "get_engine", lambda: engine)
    df = pd.DataFrame([{"流水号": "SN001", "批次号": "B1", "机型": "M1"}])
    inserted = inventory_crud.append_import_staging(df)
    assert inserted == 1
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(plan_import)")).fetchall()]
        assert "状态" in cols
        row = conn.execute(text("SELECT 状态 FROM plan_import WHERE 流水号='SN001'")).fetchone()
        assert row is not None
        assert row[0] == "待入库"


def test_append_import_staging_transaction_rollback(monkeypatch):
    engine = _build_engine_with_plan_import(include_status=True)
    monkeypatch.setattr(inventory_crud, "get_engine", lambda: engine)
    origin_to_sql = pd.DataFrame.to_sql

    def _raise_to_sql(self, *args, **kwargs):
        raise RuntimeError("mock insert failed")

    monkeypatch.setattr(pd.DataFrame, "to_sql", _raise_to_sql)
    try:
        df = pd.DataFrame([{"流水号": "SN002", "批次号": "B2", "机型": "M2", "状态": "待入库"}])
        result = inventory_crud.append_import_staging_transactional(df)
        assert result["ok"] is False
        assert result["error_code"] == "E_IMPORT_TXN_ROLLBACK"
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM plan_import")).scalar()
            assert count == 0
    finally:
        monkeypatch.setattr(pd.DataFrame, "to_sql", origin_to_sql)

