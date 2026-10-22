from unittest.mock import MagicMock
import pytest
from crud.workflows import create_reinbound_tasks, _finish_reverse_execution

@pytest.mark.parametrize('key', ['customer-order-shipped', 'customer-machine-plan'])
def test_forward_completion_does_not_validate_reverse_policy(key):
    conn = MagicMock()
    instance = {'id': 1, 'instance_no': 'WF-test', 'workflow_key': key}
    lease = {'id': 2, 'lease_token': 'test'}
    assert create_reinbound_tasks(conn, instance, force=False) == []
    conn.execute.assert_not_called()
    _finish_reverse_execution(conn, instance, lease, 'admin', {}, force_reinbound=False)
    assert any('UPDATE workflow_instances SET status=' in str(call.args[0]) and call.args[1]['status'] == '已完成' for call in conn.execute.call_args_list)
