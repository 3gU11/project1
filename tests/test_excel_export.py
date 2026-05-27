# -*- coding: utf-8 -*-
import pandas as pd
import io
from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import create_access_token

client = TestClient(app)


def auth_headers():
    token = create_access_token(subject="boss_tester", extra={"role": "Boss", "name": "老板"})
    return {"Authorization": f"Bearer {token}"}


def test_export_production_history(monkeypatch):
    import api.routes.planning as planning_route
    import pandas
    
    # Mock get_engine to avoid actual DB connection
    class MockConn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    class MockEngine:
        def connect(self):
            return MockConn()
            
    monkeypatch.setattr(planning_route, "get_engine", lambda: MockEngine())
    
    dummy_df = pd.DataFrame([
        {
            "\u673a\u53f0ID": "U001",
            "\u4ea7\u7ebf": "\u4ea7\u7ebf1",
            "\u6279\u6b21\u53f7": "\u7b2c 1 \u6279",
            "\u673a\u578b": "G-1",
            "\u5408\u540c\u53f7": "HT-001",
            "\u5ba2\u6237\u540d": "\u5f20\u4e09",
            "\u7ecf\u9500\u5546": "\u7ecf\u9500\u5546A",
            "\u72b6\u6001": "\u751f\u4ea7\u4e2d",
            "\u9884\u8ba1\u5165\u5e93\u65f6\u95f4": "2026-05-25 12:00:00",
            "\u9501\u5b9a\u72b6\u6001": "\u5426",
            "\u5907\u6ce8": "\u6d4b\u8bd5\u5907\u6ce8",
            "\u6392\u4ea7\u4e0a\u7ebf\u65f6\u95f4": "2026-05-25 08:00:00",
            "\u5b8c\u5de5\u65f6\u95f4": None
        }
    ])
    
    # Mock pandas.read_sql
    monkeypatch.setattr(pandas, "read_sql", lambda *args, **kwargs: dummy_df)
    
    resp = client.get(
        "/api/v1/planning/export-production-history",
        headers=auth_headers()
    )
    
    if resp.status_code != 200:
        print("ERROR_RESPONSE_BODY:", resp.text.encode('utf-8'))
        
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=production_history_" in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].endswith(".xlsx")
    
    excel_file = io.BytesIO(resp.content)
    df_read = pd.read_excel(excel_file, sheet_name='\u6392\u4ea7\u53f0\u8d26')
    assert df_read.shape[0] == 1
    assert list(df_read.columns) == ["批次号", "300", "400", "500", "600", "7055", "8055", "8060", "合计", "预计入库时间"]
    assert df_read.iloc[0]["批次号"] == "第 1 批"
    assert "G-1 测试备注" in str(df_read.iloc[0]["300"])
    assert int(df_read.iloc[0]["合计"]) == 1
    assert df_read.iloc[0]["预计入库时间"] == "预计2026. 5. 25"


def test_export_excel_generic():
    payload = {
        "filename": "test_export",
        "sheet_name": "TestSheet",
        "headers": ["A", "B", "C"],
        "rows": [
            [1, "hello", 3.14],
            [2, "world", 2.718]
        ]
    }
    
    resp = client.post(
        "/api/v1/planning/export-excel",
        json=payload,
        headers=auth_headers()
    )
    
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert resp.headers["content-disposition"] == "attachment; filename=test_export.xlsx"
    
    excel_file = io.BytesIO(resp.content)
    df_read = pd.read_excel(excel_file, sheet_name='TestSheet')
    assert df_read.shape[0] == 2
    assert list(df_read.columns) == ["A", "B", "C"]
    assert df_read.iloc[0]["B"] == "hello"
    assert df_read.iloc[1]["C"] == 2.718


def test_export_production_history_model_classification(monkeypatch):
    import api.routes.planning as planning_route
    import pandas
    
    class MockConn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    class MockEngine:
        def connect(self):
            return MockConn()
            
    monkeypatch.setattr(planning_route, "get_engine", lambda: MockEngine())
    
    # Unit with FR-400G and FR-400XS(PRO) under '06-01' batch code.
    # SPECIAL should have its own column.
    dummy_df = pd.DataFrame([
        {
            "机台ID": "U001", "产线": "产线1", "批次号": "06-01", "机型": "FR-400G",
            "合同号": "HT-001", "客户名": "张三", "经销商": "经销商A", "状态": "生产中",
            "预计入库时间": "2026-05-25 12:00:00", "锁定状态": "否", "备注": "后导电",
            "排产上线时间": "2026-05-25 08:00:00", "完工时间": None
        },
        {
            "机台ID": "U002", "产线": "产线1", "批次号": "06-01", "机型": "FR-400XS(PRO)",
            "合同号": "HT-002", "客户名": "李四", "经销商": "经销商B", "状态": "生产中",
            "预计入库时间": "2026-05-25 12:00:00", "锁定状态": "否", "备注": None,
            "排产上线时间": "2026-05-25 08:00:00", "完工时间": None
        },
        {
            "机台ID": "U003", "产线": "产线2", "批次号": "06-01", "机型": "SPECIAL",
            "合同号": "HT-003", "客户名": "王五", "经销商": "经销商C", "状态": "生产中",
            "预计入库时间": "2026-05-25 12:00:00", "锁定状态": "否", "备注": "定制备注",
            "排产上线时间": "2026-05-25 08:00:00", "完工时间": None
        }
    ])
    
    monkeypatch.setattr(pandas, "read_sql", lambda *args, **kwargs: dummy_df)
    
    resp = client.get(
        "/api/v1/planning/export-production-history",
        headers=auth_headers()
    )
    
    assert resp.status_code == 200
    excel_file = io.BytesIO(resp.content)
    df_read = pd.read_excel(excel_file, sheet_name='排产台账')
    
    # We expect columns to be the fixed headers: ["批次号", "300", "400", "500", "600", "7055", "8055", "8060", "合计", "预计入库时间"]
    assert list(df_read.columns) == ["批次号", "300", "400", "500", "600", "7055", "8055", "8060", "合计", "预计入库时间"]
    assert df_read.shape[0] == 2
    assert df_read.iloc[0]["批次号"] == "06-01"
    # Column "400" should contain FR-400G in first row and FR-400XS in second row
    assert "FR-400G 后导电" in str(df_read.iloc[0]["400"])
    assert "FR-400XS(PRO)" in str(df_read.iloc[1]["400"])
    # Column "300" should contain SPECIAL custom remark in first row (since it matched "300")
    assert "SPECIAL" in str(df_read.iloc[0]["300"])
    assert "定制备注" in str(df_read.iloc[0]["300"])


def test_export_tracking_sheet(monkeypatch):
    import api.routes.planning as planning_route
    import pandas
    
    class MockConn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    class MockEngine:
        def connect(self):
            return MockConn()
            
    monkeypatch.setattr(planning_route, "get_engine", lambda: MockEngine())
    
    dummy_df_ledger = pd.DataFrame([
        {
            "机台ID": "U001", "产线": "产线1", "批次号": "06-01", "机型": "FR-400G",
            "合同号": "HT-001", "客户名": "张三", "经销商": "经销商A", "状态": "生产中",
            "预计入库时间": "2026-05-25 12:00:00", "锁定状态": 0, "备注": "后导电",
            "排产上线时间": "2026-05-25 08:00:00", "完工时间": None, "流水号": "96-01-240"
        }
    ])
    
    dummy_df_pending = pd.DataFrame([
        {
            "机台ID": "U002", "产线": "待排产队列", "批次号": "06-02", "机型": "FH-300C",
            "合同号": "HT-002", "客户名": "李四", "经销商": "经销商B", "状态": "待排产",
            "预计入库时间": "2026-05-26 00:00:00", "锁定状态": 0, "备注": "无备注",
            "排产上线时间": "2026-05-25 09:00:00", "完工时间": None, "流水号": None
        }
    ])
    
    def mock_read_sql(sql_query, conn):
        q_str = str(sql_query).lower()
        if "b.status" in q_str:
            assert "b.status in ('confirmed', 'in_production')" in q_str
        if "pending" in q_str:
            return dummy_df_pending
        else:
            return dummy_df_ledger
            
    monkeypatch.setattr(pandas, "read_sql", mock_read_sql)
    
    resp = client.get(
        "/api/v1/planning/export-production-history",
        headers=auth_headers()
    )
    
    assert resp.status_code == 200
    excel_file = io.BytesIO(resp.content)
    
    xl = pd.ExcelFile(excel_file)
    assert "排产台账" in xl.sheet_names
    assert "跟踪单" in xl.sheet_names
    
    df_tracking = pd.read_excel(excel_file, sheet_name="跟踪单")
    assert list(df_tracking.columns) == ["生产批次", "型号", "生产编号"]
    assert df_tracking.shape[0] == 2
    
    assert df_tracking.iloc[0]["生产批次"] == "06-01"
    assert df_tracking.iloc[0]["型号"] == "FR-400G 后导电"
    assert df_tracking.iloc[0]["生产编号"] == "96-01-240"
    
    assert df_tracking.iloc[1]["生产批次"] == "06-02"
    assert df_tracking.iloc[1]["型号"] == "FH-300C 无备注"
    assert df_tracking.iloc[1]["生产编号"] == "U002"


def test_export_sheet_individual(monkeypatch):
    import api.routes.planning as planning_route
    import pandas
    
    class MockConn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    class MockEngine:
        def connect(self):
            return MockConn()
            
    monkeypatch.setattr(planning_route, "get_engine", lambda: MockEngine())
    
    dummy_df_ledger = pd.DataFrame([
        {
            "机台ID": "U001", "产线": "产线1", "批次号": "06-01", "机型": "FR-400G",
            "合同号": "HT-001", "客户名": "张三", "经销商": "经销商A", "状态": "生产中",
            "预计入库时间": "2026-05-25 12:00:00", "锁定状态": 0, "备注": "后导电",
            "排产上线时间": "2026-05-25 08:00:00", "完工时间": None, "流水号": "96-01-240"
        }
    ])
    
    dummy_df_pending = pd.DataFrame([
        {
            "机台ID": "U002", "产线": "待排产队列", "批次号": "06-02", "机型": "FH-300C",
            "合同号": "HT-002", "客户名": "李四", "经销商": "经销商B", "状态": "待排产",
            "预计入库时间": "2026-05-26 00:00:00", "锁定状态": 0, "备注": "无备注",
            "排产上线时间": "2026-05-25 09:00:00", "完工时间": None, "流水号": None
        }
    ])
    
    def mock_read_sql(sql_query, conn):
        q_str = str(sql_query).lower()
        if "b.status" in q_str:
            assert "b.status in ('confirmed', 'in_production')" in q_str
        if "pending" in q_str:
            return dummy_df_pending
        else:
            return dummy_df_ledger
            
    monkeypatch.setattr(pandas, "read_sql", mock_read_sql)
    
    # 1. Test sheet=tracking only
    resp = client.get(
        "/api/v1/planning/export-production-history?sheet=tracking",
        headers=auth_headers()
    )
    assert resp.status_code == 200
    excel_file = io.BytesIO(resp.content)
    xl = pd.ExcelFile(excel_file)
    assert "跟踪单" in xl.sheet_names
    assert "排产台账" not in xl.sheet_names
    
    df_tracking = pd.read_excel(excel_file, sheet_name="跟踪单")
    assert df_tracking.shape[0] == 2
    
    # 2. Test sheet=ledger only
    resp2 = client.get(
        "/api/v1/planning/export-production-history?sheet=ledger",
        headers=auth_headers()
    )
    assert resp2.status_code == 200
    excel_file2 = io.BytesIO(resp2.content)
    xl2 = pd.ExcelFile(excel_file2)
    assert "排产台账" in xl2.sheet_names
    assert "跟踪单" not in xl2.sheet_names



