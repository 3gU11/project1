from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError
from crud import dealer_orders as orders


def error(code):
    return OperationalError('SELECT summary', {}, Exception(code, 'schema changed'))


def test_list_restarts_transaction_after_schema_change(monkeypatch):
    engine = MagicMock()
    first, second = MagicMock(), MagicMock()
    engine.begin.side_effect = [first, second]
    first.__enter__.return_value.execute.side_effect = error(1412)
    second.__enter__.return_value.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(orders, 'get_engine', lambda: engine)
    monkeypatch.setattr(orders, 'ensure_dealer_order_tables', lambda: None)
    assert orders.list_dealer_orders()['data'] == []
    assert engine.begin.call_count == 2
    assert first.__exit__.call_args.args[0] is OperationalError


def test_preview_restarts_transaction_without_swallowing_business_error(monkeypatch):
    engine = MagicMock()
    first, second = MagicMock(), MagicMock()
    engine.begin.side_effect = [first, second]
    first.__enter__.return_value.execute.side_effect = error(1412)
    second.__enter__.return_value.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(orders, 'get_engine', lambda: engine)
    monkeypatch.setattr(orders, 'ensure_dealer_order_tables', lambda: None)
    with pytest.raises(ValueError, match='订单不存在'):
        orders.preview_dealer_order('missing')
    assert engine.begin.call_count == 2


@pytest.mark.parametrize('code,expected_attempts', [(1412, 3), (2006, 1)])
def test_list_bounds_retry_and_propagates_other_errors(monkeypatch, code, expected_attempts):
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value.execute.side_effect = error(code)
    monkeypatch.setattr(orders, 'get_engine', lambda: engine)
    monkeypatch.setattr(orders, 'ensure_dealer_order_tables', lambda: None)
    with pytest.raises(OperationalError):
        orders.list_dealer_orders()
    assert engine.begin.call_count == expected_attempts
