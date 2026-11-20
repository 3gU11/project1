from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from crud import workflows


class LeaseEngine:
    def __init__(self, failures=(), status='已通过', active=None):
        self.failures = list(failures)
        self.status = status
        self.active = active
        self.events = []
        self.statements = []
        self.in_transaction = False

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

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        result = Mock()
        if 'FROM workflow_instances' in sql:
            assert 'FOR UPDATE' in sql
            result.mappings.return_value.first.return_value = {'id': 1, 'status': self.status}
        elif 'SELECT * FROM workflow_execution_attempts' in sql:
            assert 'FOR UPDATE' not in sql  # No empty-range lock before INSERT.
            result.mappings.return_value.first.return_value = self.active
        elif 'MAX(attempt_no)' in sql:
            result.scalar.return_value = 2
        elif 'INSERT INTO workflow_execution_attempts' in sql:
            if self.failures:
                code = self.failures.pop(0)
                raise OperationalError(sql, params, Exception(code, 'database error'))
            assert params['attempt'] == 3
        return result


def setup_engine(monkeypatch, engine):
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    monkeypatch.setattr('time.sleep', lambda _: None)


def test_deadlock_retries_whole_transaction_after_rollback(monkeypatch):
    engine = LeaseEngine([1213])
    setup_engine(monkeypatch, engine)
    result = workflows.acquire_execution_lease('WF-1', 'inbound')
    assert result['attempt_no'] == 3
    assert engine.events == ['begin', 'rollback', 'begin', 'commit']
    assert sum('UPDATE workflow_instances' in sql for sql in engine.statements) == 1


def test_deadlock_retries_are_bounded(monkeypatch):
    engine = LeaseEngine([1213, 1213, 1213])
    setup_engine(monkeypatch, engine)
    with pytest.raises(OperationalError):
        workflows.acquire_execution_lease('WF-1', 'inbound')
    assert engine.events == ['begin', 'rollback'] * 3


@pytest.mark.parametrize('code', [1205, 2006, 2013])
def test_other_database_errors_are_not_replayed(monkeypatch, code):
    engine = LeaseEngine([code])
    setup_engine(monkeypatch, engine)
    with pytest.raises(OperationalError):
        workflows.acquire_execution_lease('WF-1', 'inbound')
    assert engine.events == ['begin', 'rollback']


@pytest.mark.parametrize('status,active', [('执行中', None), ('已通过', {'id': 9})])
def test_existing_execution_cannot_acquire_another_lease(monkeypatch, status, active):
    engine = LeaseEngine(status=status, active=active)
    setup_engine(monkeypatch, engine)
    with pytest.raises(ValueError):
        workflows.acquire_execution_lease('WF-1', 'inbound')
    assert not any('INSERT' in sql for sql in engine.statements)
    assert engine.events == ['begin', 'rollback']
