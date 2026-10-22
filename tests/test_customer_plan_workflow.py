import json
from unittest.mock import MagicMock, patch
import pytest
from api.routes import inventory
from crud import workflows


def test_planning_submits_without_saving_before_approval():
    payload = inventory.CustomerMachinePlanPayload(serial_nos=['s1'], project_name='project')
    with patch.object(inventory, 'ensure_customer_plan_table'), patch('api.routes.workflows.submit_reverse_instance', return_value={'data': {'instance_no': 'WF-plan', 'status': '审批中'}}) as submit, patch.object(inventory, 'persist_customer_machine_plans') as save:
        result = inventory.save_customer_machine_plans(payload, current_user={'username': 'planner'})
        assert '审批中' in result['message']
        assert submit.call_args.args[0].execution_data['project_name'] == 'project'
        save.assert_not_called()


def test_plan_executor_completes_inside_same_transaction():
    conn = MagicMock()
    instance = {'id': 1, 'workflow_key': 'customer-machine-plan', 'status': '执行中', 'initiator_id': 'planner', 'target_state_snapshot': json.dumps({'serial_nos': ['s1'], 'project_name': 'approved'})}
    lease = {'id': 2}
    items = [{'object_type': '机台', 'object_id': 's1', 'before_state': json.dumps({'状态': '已出库'})}]
    responses = [instance, lease, items, [{'流水号': 's1', '状态': '已出库'}]]
    conn.execute.side_effect = [MagicMock(**{'mappings.return_value.first.return_value': r, 'mappings.return_value.all.return_value': r}) for r in responses]
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    with patch.object(workflows, 'get_engine', return_value=engine), patch.object(inventory, 'ensure_customer_plan_table'), patch.object(workflows, '_assert_lease_alive'), patch.object(inventory, 'persist_customer_machine_plans') as save, patch.object(workflows, '_finish_reverse_execution') as finish:
        assert workflows.execute_customer_machine_plan('WF-plan', 'reviewer')['status'] == '已完成'
        assert save.call_args.args[0] is conn
        assert save.call_args.args[1].project_name == 'approved'
        assert save.call_args.args[2] == 'planner'
        assert finish.call_args.args[0] is conn
        save.side_effect = ValueError('save failed')
        conn.execute.side_effect = [MagicMock(**{'mappings.return_value.first.return_value': r, 'mappings.return_value.all.return_value': r}) for r in responses]
        finish.reset_mock()
        with pytest.raises(ValueError, match='save failed'):
            workflows.execute_customer_machine_plan('WF-plan', 'reviewer')
        finish.assert_not_called()
        assert engine.begin.return_value.__exit__.call_args.args[0] is ValueError
