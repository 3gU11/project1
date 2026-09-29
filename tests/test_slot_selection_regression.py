"""Warehouse validation must reject invalid destinations before any DB write."""
import pytest
from crud import inventory


@pytest.mark.parametrize('name', ['inbound_to_slot', 'inbound_to_slot_v2'])
@pytest.mark.parametrize('transfer', [False, True])
@pytest.mark.parametrize('slot', ['MISSING', '老厂不存在的库位'])
def test_unknown_slot_rejected_without_database_access(monkeypatch, name, transfer, slot):
    monkeypatch.setattr(inventory, 'get_warehouse_layout', lambda _: {
        'layout_json': {'slots': [{'code': 'A01', 'status': ''}]}})
    def forbidden():
        pytest.fail('Invalid destination reached database access')
    monkeypatch.setattr(inventory, 'get_engine', forbidden)
    result = getattr(inventory, name)('TEST-SERIAL', slot, is_transfer=transfer)
    assert result['ok'] is False
    assert result['code'] == 'E_SLOT_NOT_FOUND'


@pytest.mark.parametrize('name', ['inbound_to_slot', 'inbound_to_slot_v2'])
@pytest.mark.parametrize('status', ['锁定', '异常'])
def test_layout_whitespace_cannot_bypass_locked_slot(monkeypatch, name, status):
    monkeypatch.setattr(inventory, 'get_warehouse_layout', lambda _: {
        'layout_json': {'slots': [{'code': ' A 01 ', 'status': status}]}})
    def forbidden():
        pytest.fail('Locked destination reached database access')
    monkeypatch.setattr(inventory, 'get_engine', forbidden)
    result = getattr(inventory, name)('TEST-SERIAL', 'A01', is_transfer=True)
    assert result['code'] == 'E_SLOT_LOCKED'
