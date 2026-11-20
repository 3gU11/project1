from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from crud import forward_entries, workflows
from api.routes import workflows as workflow_routes


class _Tx:
    def __init__(self):
        self.in_transaction = False
        self.events = []

    @contextmanager
    def begin(self):
        assert not self.in_transaction
        self.in_transaction = True
        self.events.append('begin')
        try:
            yield self
        except Exception:
            self.events.append('rollback')
            raise
        else:
            self.events.append('commit')
        finally:
            self.in_transaction = False


class CleanupEngine(_Tx):
    """Fake engine for release_unstarted_instance."""

    def __init__(self, status='已通过', active=None):
        super().__init__()
        self.status = status
        self.active = active
        self.statements = []

    def execute(self, statement, params=None):
        sql = ' '.join(str(statement).split())
        self.statements.append(sql)
        result = Mock()
        if 'FROM workflow_instances' in sql and 'FOR UPDATE' in sql:
            result.mappings.return_value.first.return_value = {'id': 7, 'status': self.status}
        elif 'FROM workflow_execution_attempts' in sql:
            assert 'FOR UPDATE' not in sql
            result.scalar.return_value = self.active
        elif 'UPDATE workflow_instances' in sql:
            result.rowcount = 1
        return result


def _setup_cleanup_engine(monkeypatch, engine):
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)


def test_release_unstarted_instance_frees_machine_and_lock(monkeypatch):
    engine = CleanupEngine()
    _setup_cleanup_engine(monkeypatch, engine)
    assert workflows.release_unstarted_instance('WF-1', 'u', 'deadlock') is True
    assert any('UPDATE workflow_object_locks' in sql for sql in engine.statements)
    assert any("'执行异常'" in sql for sql in engine.statements)  # audit log
    assert engine.events == ['begin', 'commit']
    assert not any('workflow_execution_attempts' in sql and 'FOR UPDATE' in sql for sql in engine.statements)


def test_release_unstarted_instance_skips_active_lease(monkeypatch):
    engine = CleanupEngine(active=1)
    _setup_cleanup_engine(monkeypatch, engine)
    assert workflows.release_unstarted_instance('WF-1', 'u', 'deadlock') is False
    assert not any('UPDATE workflow_instances' in sql for sql in engine.statements)
    assert engine.events == ['begin', 'commit']


def test_release_unstarted_instance_skips_started_execution(monkeypatch):
    engine = CleanupEngine(status='执行中')
    _setup_cleanup_engine(monkeypatch, engine)
    assert workflows.release_unstarted_instance('WF-1', 'u', 'deadlock') is False
    assert engine.events == ['begin', 'commit']


class ForwardEngine(_Tx):
    """Fake engine for execute_forward_entry."""

    def __init__(self):
        super().__init__()
        self.statements = []

    def execute(self, statement, params=None):
        sql = ' '.join(str(statement).split())
        self.statements.append(sql)
        result = Mock()
        if 'FROM workflow_instances' in sql:
            result.mappings.return_value.first.return_value = {
                'id': 9, 'instance_no': 'WF-1', 'workflow_key': 'stock-inbound',
                'business_id': '96-10-001', 'initiator_id': 'zhaibin',
                'status': '执行中', 'target_state_snapshot': '{"payload": {}}',
            }
        elif 'FROM workflow_execution_attempts' in sql:
            result.mappings.return_value.first.return_value = {'id': 3, 'lease_token': 't'}
        elif 'FROM workflow_business_receipts' in sql:
            result.mappings.return_value.first.return_value = None
        elif 'FROM workflow_instance_items' in sql:
            result.mappings.return_value.all.return_value = []
        elif 'FROM users' in sql:
            result.mappings.return_value.first.return_value = {
                'username': 'zhaibin', 'name': 'zhaibin', 'role': 'Inbound', 'status': 'active',
            }
        return result


def test_forward_receipt_lookup_does_not_lock_absent_row(monkeypatch):
    engine = ForwardEngine()
    monkeypatch.setattr(forward_entries, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, '_assert_lease_alive', lambda *_: None)
    monkeypatch.setattr(workflows, '_finish_reverse_execution', lambda *args, **kwargs: '已完成')
    monkeypatch.setattr(forward_entries, '_invoke', lambda *_: {'ok': True, 'message': '入库成功'})

    result = forward_entries.execute_forward_entry('WF-1', 'zhaibin')

    assert result['status'] == '已完成'
    receipt_lookups = [sql for sql in engine.statements if 'FROM workflow_business_receipts' in sql]
    assert receipt_lookups
    assert all('FOR UPDATE' not in sql for sql in receipt_lookups)
    assert any('INSERT INTO workflow_business_receipts' in sql for sql in engine.statements)


def test_submit_releases_unstarted_instance_when_lease_deadlocks(monkeypatch):
    monkeypatch.setattr(workflow_routes, '_assert_reverse_permission', lambda *_: None)
    monkeypatch.setattr(workflow_routes, '_assert_reverse_precondition', lambda *_: None)
    monkeypatch.setattr(workflow_routes, 'create_reverse_instance',
                        lambda **_: ({'instance_no': 'WF-1', 'status': '已通过'}, True))
    monkeypatch.setattr(workflow_routes, 'acquire_execution_lease',
                        lambda *_: (_ for _ in ()).throw(
                            OperationalError('INSERT ...', {}, Exception(1213, 'deadlock'))))
    released = []
    monkeypatch.setattr(workflow_routes, 'release_unstarted_instance',
                        lambda *args: released.append(args) or True)

    payload = workflow_routes.ReverseCreateRequest(
        workflow_key='allocation-recall', business_type='配货单', business_id='P-1',
        idempotency_key='k-1', items=[],
    )
    with pytest.raises(HTTPException) as exc:
        workflow_routes.submit_reverse_instance(payload, {'username': 'u', 'role': 'admin'})

    assert exc.value.status_code == 500
    assert [call[:2] for call in released] == [('WF-1', 'u')]
    assert 'deadlock' in released[0][2]
