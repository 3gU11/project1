# -*- coding: utf-8 -*-
import os
import pytest
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import create_access_token
import api.routes.sandbox as sandbox_route

client = TestClient(app)


def auth_headers():
    token = create_access_token(subject="boss_tester", extra={"role": "Boss", "name": "老板"})
    return {"Authorization": f"Bearer {token}"}


def test_return_unit_to_sandbox_updates_ledger(monkeypatch):
    db_file = "test_sandbox_temp.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    engine = create_engine(f"sqlite:///{db_file}")
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    status TEXT,
                    model_type TEXT,
                    batch_no INTEGER,
                    expected_inbound_date TEXT,
                    due_date_end TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_lines (
                    production_line_id TEXT PRIMARY KEY,
                    line_name TEXT,
                    status TEXT,
                    current_batch_id TEXT,
                    updated_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS units (
                    unit_id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    slot_index INTEGER,
                    production_line_id TEXT,
                    is_locked INTEGER,
                    locked_by TEXT,
                    locked_at TEXT,
                    status TEXT,
                    contract_no TEXT,
                    customer TEXT,
                    dealer_name TEXT,
                    due_date TEXT,
                    order_remark TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_history_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id TEXT,
                    production_line_id TEXT,
                    production_line_name TEXT,
                    batch_code TEXT,
                    model_type TEXT,
                    contract_no TEXT,
                    customer TEXT,
                    dealer_name TEXT,
                    order_remark TEXT,
                    status TEXT,
                    scheduled_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS operation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT,
                    action TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    detail TEXT,
                    created_at TEXT
                )
            """))
            
            # Insert test data
            conn.execute(text("""
                INSERT INTO batches (batch_id, status, model_type, batch_no)
                VALUES ('B-OLD', 'In_Production', 'M1', 1), ('B-NEW', 'Predicted', 'M1', 2)
            """))
            conn.execute(text("""
                INSERT INTO production_lines (production_line_id, line_name, status, current_batch_id)
                VALUES ('line-1', '产线1', 'Busy', 'B-OLD')
            """))
            conn.execute(text("""
                INSERT INTO units (unit_id, batch_id, slot_index, production_line_id, is_locked, status, contract_no)
                VALUES ('U001', 'B-OLD', 1, 'line-1', 0, 'In_Production', 'C-001')
            """))
            conn.execute(text("""
                INSERT INTO production_history_ledger (unit_id, production_line_id, production_line_name, status, scheduled_at)
                VALUES ('U001', 'line-1', '产线1', 'In_Production', '2026-05-25 12:00:00')
            """))

        # Monkeypatch engine connection to strip "FOR UPDATE" which SQLite doesn't support
        orig_execute = engine.dialect.do_execute
        def mock_do_execute(cursor, statement, parameters, context=None):
            if "FOR UPDATE" in statement:
                statement = statement.replace("FOR UPDATE", "")
            # SQLite does not support datetime functions with NOW() or COLLATE,
            # so replace NOW() with CURRENT_TIMESTAMP for SQLite compatibility.
            if "NOW()" in statement:
                statement = statement.replace("NOW()", "CURRENT_TIMESTAMP")
            orig_execute(cursor, statement, parameters, context)
        monkeypatch.setattr(engine.dialect, "do_execute", mock_do_execute)

        # Mock get_engine to use our file-based SQLite DB
        monkeypatch.setattr(sandbox_route, "get_engine", lambda: engine)
        
        # Mock permissions in sandbox route
        monkeypatch.setattr(sandbox_route, "_ensure_permission", lambda user_ctx, method, go_path: None)

        # Call the endpoint to return unit to sandbox (target batch: B-NEW)
        resp = client.post(
            "/api/v1/sandbox/units/U001/return-to-sandbox",
            json={"target_batch_id": "B-NEW"},
            headers=auth_headers()
        )
        
        assert resp.status_code == 200
        
        # Verify database updates
        with engine.connect() as conn:
            # 1. Units status should be Pending, production_line_id NULL, batch_id B-NEW
            unit_row = conn.execute(text("SELECT batch_id, production_line_id, status FROM units WHERE unit_id='U001'")).fetchone()
            assert unit_row is not None
            assert unit_row[0] == "B-NEW"
            assert unit_row[1] is None
            assert unit_row[2] == "Pending"
            
            # 2. production_history_ledger status should be Cancelled
            ledger_row = conn.execute(text("SELECT status, completed_at FROM production_history_ledger WHERE unit_id='U001'")).fetchone()
            assert ledger_row is not None
            assert ledger_row[0] == "Cancelled"
            assert ledger_row[1] is not None  # completed_at should be filled
            
    finally:
        engine.dispose()
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass
