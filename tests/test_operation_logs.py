from datetime import datetime, timedelta

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from api.routes.auth import create_access_token
from crud import audit_logs


client = TestClient(app)


def test_get_operation_logs_filters_new_business_fields(monkeypatch):
    from sqlalchemy import event
    engine = create_engine("sqlite:///:memory:")
    
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        dbapi_connection.create_function("DATE_FORMAT", 2, lambda val, fmt: str(val)[:10] if val else "")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE sys_operation_log ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id TEXT, username TEXT, operate_time TEXT, "
                "module TEXT, action_type TEXT, biz_type TEXT, content TEXT)"
            )
        )
        rows = [
            {
                "user_id": "boss",
                "username": "boss_user",
                "operate_time": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "module": "sales_order",
                "action_type": "create",
                "biz_type": "order",
                "content": "创建订单：SO-001",
            },
            {
                "user_id": "admin",
                "username": "admin_user",
                "operate_time": (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"),
                "module": "user_manage",
                "action_type": "modify",
                "biz_type": "user",
                "content": "修改用户：demo",
            },
        ]
        pd.DataFrame(rows).to_sql("sys_operation_log", conn, if_exists="append", index=False)

    monkeypatch.setattr(audit_logs, "get_engine", lambda: engine)
    monkeypatch.setattr(audit_logs, "_ensure_operation_log_table", lambda: None)

    df, total = audit_logs.get_operation_logs(
        page=1,
        page_size=20,
        user="boss",
        module="sales",
        operation="create",
        biz_type="order",
        days=30,
    )

    assert total == 1
    assert list(df.columns) == ["时间", "姓名", "模块", "操作类型", "业务对象", "操作内容"]
    assert df.iloc[0]["姓名"] == "boss_user"
    assert df.iloc[0]["模块"] == "sales_order"
    assert df.iloc[0]["操作类型"] == "create"
    assert df.iloc[0]["业务对象"] == "order"
    assert df.iloc[0]["操作内容"] == "创建订单：SO-001"


def test_logs_audit_endpoint_returns_new_business_log_fields(monkeypatch):
    def fake_get_operation_logs(**kwargs):
        assert kwargs["biz_type"] == "订单"
        return (
            pd.DataFrame(
                [
                    {
                        "时间": datetime(2026, 4, 18, 10, 0, 0),
                        "姓名": "老板",
                        "模块": "销售下单",
                        "操作类型": "新增",
                        "业务对象": "订单",
                        "操作内容": "创建订单：SO-001",
                    }
                ]
            ),
            1,
        )

    monkeypatch.setattr("api.routes.logs.get_operation_logs", fake_get_operation_logs)

    token = create_access_token(subject="boss", extra={"role": "Boss", "name": "老板"})
    resp = client.get(
        "/api/v1/logs/audit",
        params={"biz_type": "订单"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["data"][0]["模块"] == "销售下单"
    assert payload["data"][0]["操作类型"] == "新增"
    assert payload["data"][0]["业务对象"] == "订单"
    assert payload["data"][0]["操作内容"] == "创建订单：SO-001"
