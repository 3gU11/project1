from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from crud import workflows


@pytest.mark.parametrize('derived_tasks,expected', [([], '已完成'), ([{'task_no': 'RI-1'}], '待派生处理')])
def test_allocation_recall_finishes_executing_instance(monkeypatch, derived_tasks, expected):
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE workflow_instances (id INTEGER, status TEXT, result TEXT, executor_id TEXT, completed_at TEXT)'))
        db.execute(text("INSERT INTO workflow_instances (id,status) VALUES (1,'执行中')"))

    class Result:
        rowcount = 1

        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def first(self):
            return self.rows[0] if self.rows else None

        def all(self):
            return self.rows

    class Connection:
        def __init__(self, db):
            self.db = db

        def execute(self, statement, params=None):
            sql = str(statement)
            if sql.startswith('UPDATE workflow_instances SET status=:status'):
                return self.db.execute(statement, params)
            if 'SELECT * FROM workflow_instances' in sql:
                return Result([{'id': 1, 'workflow_key': 'allocation-recall', 'status': '执行中'}])
            if 'SELECT * FROM workflow_execution_attempts' in sql:
                return Result([{'id': 2, 'lease_token': 'token'}])
            if 'SELECT * FROM workflow_instance_items' in sql:
                return Result([{'object_type': '机台', 'object_id': 'SN-1'}])
            if 'SELECT `流水号`,`状态`' in sql:
                return Result([{'流水号': 'SN-1', '状态': '待发货', '占用订单号': 'SO-1', 'row_version': 1}])
            return Result([])

    @contextmanager
    def begin():
        with engine.begin() as db:
            yield Connection(db)

    monkeypatch.setattr(workflows, 'get_engine', lambda: SimpleNamespace(begin=begin))
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, '_assert_lease_alive', lambda *args: None)
    monkeypatch.setattr(workflows, '_validate_machine_snapshots', lambda *args: None)
    monkeypatch.setattr(workflows, 'create_reinbound_tasks', lambda *args: derived_tasks)
    response = workflows.execute_allocation_recall('WF-1', 'tester')
    with engine.connect() as db:
        row = db.execute(text('SELECT status,result FROM workflow_instances')).one()
    assert row.status == response['status'] == expected
    assert row.result == '成功'
    engine.dispose()
