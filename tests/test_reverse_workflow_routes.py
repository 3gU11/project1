import pytest
from sqlalchemy import create_engine, text
from fastapi import HTTPException

from api.routes import workflows as workflow_routes
from api.routes.workflows import ReverseCreateRequest, router


@pytest.fixture
def shipment_engine(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE finished_goods_data (`流水号` TEXT, `状态` TEXT, `合同号` TEXT, `占用订单号` TEXT)'))
    monkeypatch.setattr(workflow_routes, 'get_engine', lambda: engine)
    yield engine
    engine.dispose()


@pytest.mark.parametrize('workflow_key', ['order-delete', 'contract-cancel'])
@pytest.mark.parametrize('status', ['已出库', '已发货', '库存中（DG-WH）'])
@pytest.mark.parametrize('role', ['Boss', 'sales'])
def test_shipped_business_is_blocked_before_workflow_creation(monkeypatch, shipment_engine, workflow_key, status, role):
    with shipment_engine.begin() as conn:
        conn.execute(text('INSERT INTO finished_goods_data VALUES (:sn,:status,:id,:id)'),
                     {'sn': 'SN-SHIPPED', 'status': status, 'id': 'BUSINESS-1'})
    monkeypatch.setattr(workflow_routes, 'create_reverse_instance', lambda **kwargs: pytest.fail('must not create approval'))
    with pytest.raises(HTTPException) as error:
        workflow_routes.submit_reverse_instance(ReverseCreateRequest(
            workflow_key=workflow_key, business_type='合同' if workflow_key == 'contract-cancel' else '订单',
            business_id='BUSINESS-1', idempotency_key='blocked-test'), {'username': 'tester', 'role': role})
    assert error.value.status_code == 409
    assert 'SN-SHIPPED' in error.value.detail


def test_reverse_workflow_routes_registered():
    paths = {route.path for route in router.routes}
    assert "/reverse/instances" in paths
    assert "/instances/{instance_no}/approve" in paths
    assert "/instances/{instance_no}/transfer" in paths
    assert "/instances/{instance_no}/execute" in paths
    assert "/instances/{instance_no}/notifications/retry" in paths


def test_outbox_and_lease_admin_routes_registered():
    paths = {route.path for route in router.routes}
    assert "/admin/outbox/claim" in paths
    assert "/admin/outbox/{event_id}/complete" in paths
    assert "/admin/outbox/{event_id}/fail" in paths
    assert "/admin/outbox/{event_id}/requeue" in paths
    assert "/admin/execution-leases/reclaim" in paths


@pytest.mark.parametrize('role,expected', [('Boss', True), ('admin', False), ('sales', False)])
def test_only_boss_submission_executes_approved_contract_automatically(monkeypatch, shipment_engine, role, expected):
    calls = []
    def create(**kwargs):
        assert kwargs['initiator_role'] == role
        return {'instance_no': 'WF-BOSS', 'status': '已通过' if expected else '审批中'}, True
    monkeypatch.setattr(workflow_routes, 'create_reverse_instance', create)
    monkeypatch.setattr(workflow_routes, 'acquire_execution_lease', lambda *args: None)
    monkeypatch.setattr(workflow_routes, 'workflow_action_for_instance', lambda no: 'cancel_contract_reinbound')
    monkeypatch.setattr(workflow_routes, 'execute_contract_cancel', lambda *args: calls.append(args) or {'status': '已完成'})
    monkeypatch.setattr(workflow_routes, 'dispatch_pending_model_notifications', lambda no: None)
    result = workflow_routes.submit_reverse_instance(ReverseCreateRequest(
        workflow_key='contract-cancel', business_type='合同', business_id='C-1', idempotency_key='test-boss'),
        {'username': 'boss-user', 'role': role})
    assert bool(calls) is expected
    assert result['data']['status'] == ('已完成' if expected else '审批中')


def test_reverse_submission_runs_automatically_and_uses_model_action(monkeypatch):
    """自动通过的逆向流程：提交后立即执行并派发通知。"""
    calls = []
    monkeypatch.setattr(workflow_routes, 'create_reverse_instance', lambda **_kwargs: ({'instance_no': 'WF-1', 'status': '已通过'}, True))
    monkeypatch.setattr(workflow_routes, 'acquire_execution_lease', lambda no, user: calls.append(('lease', no, user)))
    monkeypatch.setattr(workflow_routes, 'workflow_action_for_instance', lambda no: 'recall_allocation')
    monkeypatch.setattr(workflow_routes, 'execute_allocation_recall', lambda no, user: calls.append(('execute', no, user)) or {'instance_no': no, 'status': '待派生处理'})
    monkeypatch.setattr(workflow_routes, 'dispatch_pending_model_notifications', lambda no: calls.append(('notify', no)))

    result = workflow_routes.submit_reverse_instance(
        ReverseCreateRequest(
            workflow_key='allocation-recall', business_type='订单配货', business_id='SO-1',
            idempotency_key='allocation-recall:SO-1', items=[{'object_type': '机台', 'object_id': 'SN-1'}],
        ),
        {'username': 'shipper'},
    )

    assert result['data']['status'] == '待派生处理'
    assert calls == [('lease', 'WF-1', 'shipper'), ('execute', 'WF-1', 'shipper'), ('notify', 'WF-1')]


def test_reverse_notification_error_does_not_fail_completed_business_action(monkeypatch):
    monkeypatch.setattr(workflow_routes, 'create_reverse_instance', lambda **_kwargs: ({'instance_no': 'WF-2', 'status': '已通过'}, True))
    monkeypatch.setattr(workflow_routes, 'acquire_execution_lease', lambda *_args: None)
    monkeypatch.setattr(workflow_routes, 'workflow_action_for_instance', lambda _no: 'recall_allocation')
    monkeypatch.setattr(workflow_routes, 'execute_allocation_recall', lambda *_args: {'instance_no': 'WF-2', 'status': '已完成'})
    monkeypatch.setattr(workflow_routes, 'dispatch_pending_model_notifications', lambda _no: (_ for _ in ()).throw(RuntimeError('offline')))
    monkeypatch.setattr(workflow_routes, 'mark_execution_failure', lambda *_args: pytest.fail('business success must not be marked failed'))

    result = workflow_routes.submit_reverse_instance(
        ReverseCreateRequest(
            workflow_key='allocation-recall', business_type='订单配货', business_id='SO-2',
            idempotency_key='allocation-recall:SO-2', items=[{'object_type': '机台', 'object_id': 'SN-2'}],
        ),
        {'username': 'shipper'},
    )

    assert result['data']['status'] == '已完成'
    assert result['data']['notification_delivery_pending'] is True


def test_shipment_recall_is_rejected_because_shipped_machines_cannot_be_recalled():
    """发货撤回只允许在待发货阶段做；已发货的机台必须走退换货处理。"""
    with pytest.raises(HTTPException) as excinfo:
        workflow_routes.submit_reverse_instance(
            ReverseCreateRequest(
                workflow_key='shipment-recall', business_type='机台', business_id='SN-9',
                idempotency_key='shipment-recall:SN-9', items=[{'object_type': '机台', 'object_id': 'SN-9'}],
            ),
            {'username': 'shipper'},
        )
    assert excinfo.value.status_code == 409
    assert '退换货处理' in str(excinfo.value.detail)
