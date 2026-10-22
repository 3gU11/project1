import pytest

from crud.workflows import _advance_approved_graph, validate_workflow_snapshot, workflow_action_for_instance


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def fetchall(self):
        return []


class ConditionConnection:
    def __init__(self, machine_count):
        self.machine_count = machine_count

    def execute(self, statement, params):
        sql = str(statement)
        if 'finished_goods_data' in sql:
            return ScalarResult(self.machine_count)
        if 'workflow_instance_items' in sql:
            return ScalarResult(1)
        if 'FROM users' in sql:
            return ScalarResult(0)
        raise AssertionError(sql)


def branch_snapshot():
    return {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'approval', 'type': 'approval', 'approvalRoles': ['Boss']},
            {'id': 'condition', 'type': 'condition', 'conditionField': 'bound_machine_count', 'conditionOperator': 'gt', 'conditionValue': 0},
            {'id': 'cancel', 'type': 'execute', 'action': 'cancel_contract'},
            {'id': 'release', 'type': 'execute', 'action': 'recall_allocation'},
            {'id': 'notify', 'type': 'notify', 'notifyRoles': ['Inbound']},
            {'id': 'end-no-machines', 'type': 'end'},
            {'id': 'end-machines', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start', 'target': 'approval'},
            {'source': 'approval', 'target': 'condition'},
            {'source': 'condition', 'target': 'cancel', 'branch': 'false'},
            {'source': 'condition', 'target': 'release', 'branch': 'true'},
            {'source': 'cancel', 'target': 'end-no-machines'},
            {'source': 'release', 'target': 'notify'},
            {'source': 'notify', 'target': 'end-machines'},
        ],
    }


def test_branch_path_selects_only_the_action_and_notification_on_that_path():
    snapshot = branch_snapshot()
    validate_workflow_snapshot(snapshot)

    no_machines = _advance_approved_graph(
        ConditionConnection(0),
        {'id': 1, 'instance_no': 'WF-1', 'business_id': 'C-1'},
        snapshot,
    )
    has_machines = _advance_approved_graph(
        ConditionConnection(2),
        {'id': 2, 'instance_no': 'WF-2', 'business_id': 'C-2'},
        snapshot,
    )

    assert 'cancel' in no_machines['visited_nodes']
    assert 'release' not in no_machines['visited_nodes']
    assert no_machines['pending_notification_nodes'] == []
    assert 'release' in has_machines['visited_nodes']
    assert 'cancel' not in has_machines['visited_nodes']
    assert has_machines['pending_notification_nodes'] == ['notify']


def test_condition_requires_supported_field_and_explicit_true_false_edges():
    snapshot = branch_snapshot()
    snapshot['nodes'][2]['conditionField'] = 'arbitrary_sql'
    with pytest.raises(ValueError, match='不支持的流程条件字段'):
        validate_workflow_snapshot(snapshot)

    snapshot = branch_snapshot()
    snapshot['edges'][2].pop('branch')
    with pytest.raises(ValueError, match='必须标记 true 或 false'):
        validate_workflow_snapshot(snapshot)


def test_workflow_action_resolution_requires_existing_instance(monkeypatch):
    class FakeConnection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args, **_kwargs):
            class Result:
                def mappings(self): return self
                def first(self): return None
            return Result()

    class FakeEngine:
        def connect(self): return FakeConnection()

    monkeypatch.setattr('crud.workflows.get_engine', lambda: FakeEngine())
    with pytest.raises(ValueError, match='流程实例不存在'):
        workflow_action_for_instance('missing')


def test_graph_validation_allows_actions_on_separate_branches():
    snapshot = branch_snapshot()
    assert validate_workflow_snapshot(snapshot) is snapshot


def test_order_delete_branch_actions_are_compatible():
    snapshot = branch_snapshot()
    snapshot['nodes'][3]['action'] = 'delete_order'
    snapshot['nodes'][4]['action'] = 'delete_order_reinbound'
    assert validate_workflow_snapshot(snapshot, 'order-delete') is snapshot


def test_graph_validation_rejects_two_approvals_on_one_path():
    snapshot = {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'approval-a', 'type': 'approval', 'approvalRoles': ['Boss']},
            {'id': 'approval-b', 'type': 'approval', 'approvalRoles': ['Admin']},
            {'id': 'end', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start', 'target': 'approval-a'},
            {'source': 'approval-a', 'target': 'approval-b'},
            {'source': 'approval-b', 'target': 'end'},
        ],
    }
    with pytest.raises(ValueError, match='只支持一个审批节点'):
        validate_workflow_snapshot(snapshot)


def test_graph_validation_rejects_two_actions_on_one_path():
    snapshot = {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'first', 'type': 'execute', 'action': 'cancel_contract'},
            {'id': 'second', 'type': 'execute', 'action': 'delete_order'},
            {'id': 'end', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start', 'target': 'first'},
            {'source': 'first', 'target': 'second'},
            {'source': 'second', 'target': 'end'},
        ],
    }
    with pytest.raises(ValueError, match='同一流程路径只支持一个业务执行节点'):
        validate_workflow_snapshot(snapshot)


def test_graph_validation_rejects_branch_that_bypasses_shared_approval():
    snapshot = {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'condition', 'type': 'condition', 'conditionField': 'item_count', 'conditionOperator': 'gt', 'conditionValue': 0},
            {'id': 'approval', 'type': 'approval', 'approvalRoles': ['Boss']},
            {'id': 'execute-a', 'type': 'execute', 'action': 'cancel_contract'},
            {'id': 'execute-b', 'type': 'execute', 'action': 'cancel_contract'},
            {'id': 'end-a', 'type': 'end'},
            {'id': 'end-b', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start', 'target': 'condition'},
            {'source': 'condition', 'target': 'approval', 'branch': 'true'},
            {'source': 'condition', 'target': 'execute-b', 'branch': 'false'},
            {'source': 'approval', 'target': 'execute-a'},
            {'source': 'execute-a', 'target': 'end-a'},
            {'source': 'execute-b', 'target': 'end-b'},
        ],
    }
    with pytest.raises(ValueError, match='所有流程分支都必须经过该审批节点'):
        validate_workflow_snapshot(snapshot, 'contract-cancel')


def test_graph_validation_rejects_ambiguous_regular_node_fanout():
    snapshot = {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'notify', 'type': 'notify', 'notifyRoles': ['Inbound']},
            {'id': 'a', 'type': 'end'},
            {'id': 'b', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start', 'target': 'notify'},
            {'source': 'notify', 'target': 'a'},
            {'source': 'notify', 'target': 'b'},
        ],
    }
    with pytest.raises(ValueError, match='必须且只能有一条后续连线'):
        validate_workflow_snapshot(snapshot)


def test_reverse_model_requires_compatible_action_on_every_path():
    snapshot = {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'execute', 'type': 'execute', 'action': 'recall_allocation'},
            {'id': 'end', 'type': 'end'},
        ],
        'edges': [{'source': 'start', 'target': 'execute'}, {'source': 'execute', 'target': 'end'}],
    }
    with pytest.raises(ValueError, match='不适用于流程'):
        validate_workflow_snapshot(snapshot, 'contract-cancel')

    snapshot['nodes'][1]['action'] = 'cancel_contract'
    assert validate_workflow_snapshot(snapshot, 'contract-cancel') is snapshot


def test_shipment_recall_model_cannot_add_an_approval_node():
    snapshot = {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'approval', 'type': 'approval', 'approvalRoles': ['Boss']},
            {'id': 'execute', 'type': 'execute', 'action': 'recall_shipment'},
            {'id': 'end', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start', 'target': 'approval'},
            {'source': 'approval', 'target': 'execute'},
            {'source': 'execute', 'target': 'end'},
        ],
    }
    with pytest.raises(ValueError, match='发货撤回按业务规则自动通过'):
        validate_workflow_snapshot(snapshot, 'shipment-recall')
