from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from crud import forward_entries as entries
from crud.workflows import FORWARD_ENTRY_ACTIONS, validate_workflow_snapshot


@pytest.mark.parametrize('key,action', FORWARD_ENTRY_ACTIONS.items())
def test_forward_models_require_matching_action_and_allow_approval(key, action):
    graph = {'nodes': [
        {'id': 's', 'type': 'start'},
        {'id': 'a', 'type': 'approval', 'approvalRoles': ['Boss']},
        {'id': 'x', 'type': 'execute', 'action': action},
        {'id': 'e', 'type': 'end'},
    ], 'edges': [{'source': a, 'target': b} for a, b in [('s', 'a'), ('a', 'x'), ('x', 'e')]]}
    validate_workflow_snapshot(graph, key)
    graph['nodes'][2]['action'] = 'cancel_contract'
    with pytest.raises(ValueError, match='不适用'):
        validate_workflow_snapshot(graph, key)


class Command(BaseModel):
    serial_no: str = 'M-1'
    slot_code: str = 'A-1'


def test_submission_retains_command_and_returns_pending_without_business_execution(monkeypatch):
    from api.routes import workflows
    submit = MagicMock(return_value={'data': {'status': '审批中', 'instance_no': 'WF-1'}})
    monkeypatch.setattr(workflows, 'submit_reverse_instance', submit)
    invoke = MagicMock()
    monkeypatch.setattr(entries, '_invoke', invoke)
    result = entries.submit_entry('stock-inbound', Command(), {'username': 'inbound'})
    assert result['approval_pending'] is True
    assert result['instance_no'] == 'WF-1'
    command, user = submit.call_args.args
    assert command.execution_data['payload'] == {'serial_no': 'M-1', 'slot_code': 'A-1'}
    assert user['username'] == 'inbound'
    invoke.assert_not_called()
    assert not entries.submitting()


def test_replay_does_not_submit_a_second_workflow(monkeypatch):
    from api.routes import workflows
    submit = MagicMock()
    monkeypatch.setattr(workflows, 'submit_reverse_instance', submit)
    token = entries._replay.set({'order_id': 'SO-fixed'})
    try:
        assert entries.submit_entry('order-create', Command(), {'username': 'boss'}) is None
        assert entries.stable_order_id('new-id') == 'SO-fixed'
    finally:
        entries._replay.reset(token)
    submit.assert_not_called()


@pytest.mark.parametrize('receipt_status', ['成功', '执行中'])
def test_existing_receipt_never_repeats_business_action(monkeypatch, receipt_status):
    from crud import workflows
    conn = MagicMock()
    instance = {'id': 1, 'status': '执行中', 'instance_no': 'WF-1'}
    lease = {'id': 2}
    responses = []
    for row in [instance, lease, {'status': receipt_status, 'result': '{"message":"saved"}'}]:
        response = MagicMock()
        response.mappings.return_value.first.return_value = row
        responses.append(response)
    conn.execute.side_effect = responses
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    monkeypatch.setattr(entries, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, '_assert_lease_alive', MagicMock())
    finish = MagicMock()
    monkeypatch.setattr(workflows, '_finish_reverse_execution', finish)
    invoke = MagicMock()
    monkeypatch.setattr(entries, '_invoke', invoke)
    if receipt_status == '成功':
        assert entries.execute_forward_entry('WF-1', 'boss')['status'] == '已完成'
        finish.assert_called_once()
    else:
        with pytest.raises(ValueError, match='不会自动重复执行'):
            entries.execute_forward_entry('WF-1', 'boss')
        finish.assert_not_called()
    invoke.assert_not_called()
