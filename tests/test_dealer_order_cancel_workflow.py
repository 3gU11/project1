"""经销商订单取消逆向流程注册、默认图、执行器与路由的单元测试。

不依赖 MySQL：默认图/幂等补齐用 sqlite 夹具，执行器用 MagicMock 连接，
crud.dealer_order_cancel（并行开发中的级联内核）通过 sys.modules 打桩，
测试只验证流程框架这一侧的职责边界。
"""
import json
import sys
import types
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from api.routes import dealer_orders as dealer_order_routes
from api.routes import workflows as workflow_routes
from crud import workflows


CANCEL_KEY = 'dealer-order-cancel'
CANCEL_ACTION = 'cancel_dealer_order'
CANCEL_EXECUTOR = 'execute_dealer_order_cancel'


# --------------------------------------------------------------------------- #
# 注册项与编排策略
# --------------------------------------------------------------------------- #
def test_dealer_order_cancel_is_registered_as_reverse_workflow():
    assert CANCEL_KEY in workflows.REVERSE_WORKFLOW_KEYS
    assert workflows.REVERSE_WORKFLOW_RULES[CANCEL_KEY] == {
        'approval': 'automatic',
        'derived_task': 'conditional-reinbound',
    }
    # 自动通过只是默认策略，审批与否由模型图决定；rule 只是服务端策略声明。
    assert workflows.reverse_workflow_rule(CANCEL_KEY)['approval'] == 'automatic'


def test_cancel_dealer_order_action_maps_to_executor():
    assert workflows.WORKFLOW_ACTIONS[CANCEL_ACTION] == CANCEL_EXECUTOR
    assert workflows.WORKFLOW_ACTIONS[CANCEL_ACTION] == workflows.execute_dealer_order_cancel.__name__
    assert CANCEL_ACTION in workflows.REVERSE_WORKFLOW_ACTIONS[CANCEL_KEY]
    # 流程模型编辑器的动作白名单由服务端下发，必须包含新动作。
    catalog = workflows.workflow_editor_catalog()
    assert CANCEL_ACTION in catalog['actions'][CANCEL_KEY]


def test_action_executor_resolves_cancel_dealer_order():
    executor = workflow_routes._action_executor(CANCEL_ACTION)
    assert executor is workflows.execute_dealer_order_cancel
    assert workflow_routes.REVERSE_WORKFLOW_PERMISSIONS[CANCEL_KEY] == 'DEALER_ORDER_REVIEW'


def test_seed_phase1_models_includes_dealer_order_cancel(monkeypatch):
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)

    workflows.seed_phase1_models()

    params = [call.args[1] for call in conn.execute.call_args_list
              if len(call.args) > 1 and isinstance(call.args[1], dict) and 'key' in call.args[1]]
    rows = [row for row in params if row.get('key') == CANCEL_KEY]
    assert len(rows) == 1
    row = rows[0]
    assert row['name'] == '取消经销商订单'
    assert row['category'] == '订单流程'
    assert row['direction'] == '逆向'
    assert row['processing'] == '自动通过'
    assert row['object'] == '经销商订单'
    assert row['scope'] == '整单'
    assert int(row['required']) == 0


# --------------------------------------------------------------------------- #
# 默认图
# --------------------------------------------------------------------------- #
def test_dealer_order_cancel_default_graph_has_no_approval_node():
    graph = workflows.dealer_order_cancel_default_snapshot()
    nodes = {node['id']: node for node in graph['nodes']}
    assert [node['type'] for node in graph['nodes']] == ['start', 'execute', 'notify', 'end']
    assert nodes['execute']['action'] == CANCEL_ACTION
    assert nodes['execute']['targetState'] == '已取消'
    assert nodes['notify']['notifyRoles'] == ['Inbound']
    assert [(edge['source'], edge['target']) for edge in graph['edges']] == [
        ('start', 'execute'), ('execute', 'notify'), ('notify', 'end'),
    ]
    # 默认图无审批节点 => create_reverse_instance 直接走自动通过。
    assert workflows._snapshot_requires_approval(graph) is False
    # 默认图也必须能通过模型编辑器的发布校验。
    workflows.validate_workflow_snapshot(graph, CANCEL_KEY)


@pytest.fixture
def workflow_db(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE workflow_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_key TEXT NOT NULL UNIQUE,
            name TEXT, category_key TEXT, direction TEXT, processing_type TEXT,
            business_object TEXT, execution_scope TEXT, status TEXT,
            is_required INTEGER DEFAULT 0, current_version INTEGER DEFAULT 0)"""))
        conn.execute(text("""CREATE TABLE workflow_model_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            status TEXT, runtime_enabled INTEGER DEFAULT 0, node_snapshot TEXT)"""))
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    yield engine
    engine.dispose()


def test_ensure_dealer_order_cancel_model_creates_default_graph(workflow_db):
    result = workflows.ensure_dealer_order_cancel_model()
    assert result['workflow_key'] == CANCEL_KEY
    assert result['graph'] == 'default'
    assert result['updated'] is True
    assert result['version'] == 1

    with workflow_db.connect() as conn:
        model = conn.execute(text("SELECT * FROM workflow_models WHERE workflow_key=:key"),
                             {'key': CANCEL_KEY}).mappings().first()
        version = conn.execute(text("SELECT * FROM workflow_model_versions WHERE model_id=:id AND version_no=1"),
                               {'id': model['id']}).mappings().first()
    assert model['status'] == '已发布'
    assert model['processing_type'] == '自动通过'
    assert int(model['current_version']) == 1
    assert version['status'] == '已发布'
    assert int(version['runtime_enabled']) == 1
    snapshot = json.loads(version['node_snapshot'])
    assert {node['type'] for node in snapshot['nodes']} == {'start', 'execute', 'notify', 'end'}
    assert workflows._snapshot_requires_approval(snapshot) is False


def test_ensure_dealer_order_cancel_model_is_idempotent(workflow_db):
    workflows.ensure_dealer_order_cancel_model()
    again = workflows.ensure_dealer_order_cancel_model()
    assert again['updated'] is False
    assert again['graph'] == 'custom'  # 默认图已存在，第二次只读
    with workflow_db.connect() as conn:
        model_count = conn.execute(text("SELECT COUNT(*) FROM workflow_models WHERE workflow_key=:key"),
                                   {'key': CANCEL_KEY}).scalar()
        version_count = conn.execute(text("SELECT COUNT(*) FROM workflow_model_versions")).scalar()
    assert model_count == 1
    assert version_count == 1


def test_ensure_dealer_order_cancel_model_fills_seeded_placeholder(workflow_db):
    """seed_phase1_models 会先写一个没有 nodes 的占位快照，ensure 必须补默认图。"""
    with workflow_db.begin() as conn:
        conn.execute(text("""INSERT INTO workflow_models
            (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,status,current_version)
            VALUES (:key,'取消经销商订单','订单流程','逆向','自动通过','经销商订单','整单','已发布',1)"""),
            {'key': CANCEL_KEY})
        model_id = conn.execute(text("SELECT id FROM workflow_models WHERE workflow_key=:key"),
                                {'key': CANCEL_KEY}).scalar()
        conn.execute(text("""INSERT INTO workflow_model_versions
            (model_id,version_no,status,runtime_enabled,node_snapshot)
            VALUES (:id,1,'已发布',0,:snapshot)"""),
            {'id': model_id, 'snapshot': json.dumps({'phase': 1, 'runtime_enabled': False})})

    result = workflows.ensure_dealer_order_cancel_model()
    assert result['updated'] is True
    assert result['version'] == 1
    with workflow_db.connect() as conn:
        raw = conn.execute(text("SELECT node_snapshot FROM workflow_model_versions WHERE model_id=:id"),
                           {'id': result['model_id']}).scalar()
        runtime_enabled = conn.execute(text("SELECT runtime_enabled FROM workflow_model_versions WHERE model_id=:id"),
                                       {'id': result['model_id']}).scalar()
    snapshot = json.loads(raw)
    assert [node['type'] for node in snapshot['nodes']] == ['start', 'execute', 'notify', 'end']
    assert int(runtime_enabled) == 1


def test_ensure_dealer_order_cancel_model_keeps_custom_approval_graph(workflow_db):
    custom = {
        'nodes': [
            {'id': 'start', 'type': 'start', 'label': '发起'},
            {'id': 'approval', 'type': 'approval', 'label': '审批', 'approvalRoles': ['Boss']},
            {'id': 'execute', 'type': 'execute', 'label': '取消订单', 'action': CANCEL_ACTION},
            {'id': 'end', 'type': 'end', 'label': '结束'},
        ],
        'edges': [
            {'source': 'start', 'target': 'approval'},
            {'source': 'approval', 'target': 'execute'},
            {'source': 'execute', 'target': 'end'},
        ],
    }
    with workflow_db.begin() as conn:
        conn.execute(text("""INSERT INTO workflow_models
            (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,status,current_version)
            VALUES (:key,'取消经销商订单','订单流程','逆向','需要审批','经销商订单','整单','已发布',1)"""),
            {'key': CANCEL_KEY})
        model_id = conn.execute(text("SELECT id FROM workflow_models WHERE workflow_key=:key"),
                                {'key': CANCEL_KEY}).scalar()
        conn.execute(text("""INSERT INTO workflow_model_versions
            (model_id,version_no,status,runtime_enabled,node_snapshot)
            VALUES (:id,1,'已发布',1,:snapshot)"""),
            {'id': model_id, 'snapshot': json.dumps(custom, ensure_ascii=False)})

    result = workflows.ensure_dealer_order_cancel_model()
    assert result['updated'] is False
    assert result['graph'] == 'custom'
    with workflow_db.connect() as conn:
        raw = conn.execute(text("SELECT node_snapshot FROM workflow_model_versions WHERE model_id=:id"),
                           {'id': result['model_id']}).scalar()
    assert json.loads(raw) == custom
    # 管理员加了审批节点后，运行时按图判定需要审批。
    assert workflows._snapshot_requires_approval(json.loads(raw)) is True


def test_migrate_phase1_workflow_metadata_calls_ensure(monkeypatch):
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = MagicMock()
    calls = []
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, 'ensure_dealer_order_cancel_model', lambda: calls.append(True))

    workflows.migrate_phase1_workflow_metadata()

    assert calls == [True]


# --------------------------------------------------------------------------- #
# 执行器：状态机 + 租约 + 同一事务内调用级联 + 收尾
# --------------------------------------------------------------------------- #
def _query(rows=None, all_rows=None):
    result = MagicMock()
    if all_rows is not None:
        result.mappings.return_value.all.return_value = all_rows
    else:
        result.mappings.return_value.first.return_value = rows
    return result


def _cascade_stub(monkeypatch, summary=None, error=None):
    calls = []

    def fake_cascade(conn, order_no, operator, reason=''):
        calls.append({'conn': conn, 'order_no': order_no, 'operator': operator, 'reason': reason})
        if error:
            raise error
        return summary if summary is not None else {}

    module = types.ModuleType('crud.dealer_order_cancel')
    module.execute_dealer_order_cancel = fake_cascade
    module.preview_dealer_order_cancel = lambda order_no: {'order_no': order_no}
    module.cancel_dealer_order = lambda *args, **kwargs: {}
    monkeypatch.setitem(sys.modules, 'crud.dealer_order_cancel', module)
    return calls


def test_execute_dealer_order_cancel_runs_cascade_in_same_transaction(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    instance = {
        'id': 7, 'instance_no': 'WF-CANCEL-1', 'workflow_key': CANCEL_KEY,
        'status': '执行中', 'business_id': 'DO-20261112-001',
        'before_state_snapshot': json.dumps({'reason': '客户临时取消'}, ensure_ascii=False),
    }
    lease = {'id': 9, 'lease_token': 'token-9', 'status': '执行中'}
    items = [
        {'object_type': '机台', 'object_id': 'SN-1'},
        {'object_type': '经销商订单', 'object_id': 'DO-20261112-001'},
    ]
    conn.execute.side_effect = [_query(instance), _query(lease), _query(all_rows=items)]
    cascade_calls = _cascade_stub(monkeypatch, summary={
        'status': 'cancelled',
        'released_serials': ['SN-1', 'SN-2'],
        'stock': 1,
        'production': 1,
        'contracts': ['HT-1'],
        'sales_orders': ['SO-1'],
        'dealer_lines': 2,
        'cloud_event': {'event_type': 'dealer_order_cancelled'},
        'warnings': [],
    })
    finish = MagicMock(return_value='待派生处理')
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, '_assert_lease_alive', lambda _conn, _lease: None)
    monkeypatch.setattr(workflows, '_finish_reverse_execution', finish)
    monkeypatch.setattr(workflows, '_clear_order_planning_caches', lambda: None)

    result = workflows.execute_dealer_order_cancel('WF-CANCEL-1', 'worker-1')

    # 级联内核在同一事务连接上执行，reason 来自 before_state_snapshot。
    assert len(cascade_calls) == 1
    assert cascade_calls[0]['conn'] is conn
    assert cascade_calls[0]['order_no'] == 'DO-20261112-001'
    assert cascade_calls[0]['operator'] == 'worker-1'
    assert cascade_calls[0]['reason'] == '客户临时取消'
    # 收尾强制派生重入库任务，范围就是级联释放的机台。
    args, kwargs = finish.call_args
    assert args[:4] == (conn, instance, lease, 'worker-1')
    assert args[4]['workflow_key'] == CANCEL_KEY
    assert args[4]['business_id'] == 'DO-20261112-001'
    assert args[4]['snapshot_serials'] == ['SN-1']
    assert args[4]['released_serials'] == ['SN-1', 'SN-2']
    assert kwargs['force_reinbound'] is True
    assert kwargs['reinbound_object_ids'] == ['SN-1', 'SN-2']
    # 返回流程状态，同时保留级联内核自己的 status 便于排查。
    assert result['instance_no'] == 'WF-CANCEL-1'
    assert result['status'] == '待派生处理'
    assert result['cascade_status'] == 'cancelled'
    assert result['released_serials'] == ['SN-1', 'SN-2']


def test_execute_dealer_order_cancel_refuses_wrong_status(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    conn.execute.side_effect = [_query({
        'id': 7, 'instance_no': 'WF-CANCEL-2', 'workflow_key': CANCEL_KEY,
        'status': '审批中', 'business_id': 'DO-1', 'before_state_snapshot': '{}',
    })]
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    _cascade_stub(monkeypatch)

    with pytest.raises(ValueError, match='不能执行'):
        workflows.execute_dealer_order_cancel('WF-CANCEL-2', 'worker-1')


def test_execute_dealer_order_cancel_refuses_other_workflow(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    conn.execute.side_effect = [_query({
        'id': 8, 'instance_no': 'WF-OTHER', 'workflow_key': 'allocation-recall',
        'status': '执行中', 'business_id': 'SO-1', 'before_state_snapshot': '{}',
    })]
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    _cascade_stub(monkeypatch)

    with pytest.raises(ValueError, match='取消经销商订单流程'):
        workflows.execute_dealer_order_cancel('WF-OTHER', 'worker-1')


def test_execute_dealer_order_cancel_does_not_finish_when_cascade_fails(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    instance = {
        'id': 7, 'instance_no': 'WF-CANCEL-3', 'workflow_key': CANCEL_KEY,
        'status': '执行中', 'business_id': 'DO-1', 'before_state_snapshot': '{}',
    }
    lease = {'id': 9, 'lease_token': 'token-9', 'status': '执行中'}
    conn.execute.side_effect = [_query(instance), _query(lease), _query(all_rows=[])]
    _cascade_stub(monkeypatch, error=ValueError('订单存在已发货机台，不能取消'))
    finish = MagicMock()
    monkeypatch.setattr(workflows, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, '_assert_lease_alive', lambda _conn, _lease: None)
    monkeypatch.setattr(workflows, '_finish_reverse_execution', finish)

    with pytest.raises(ValueError, match='已发货'):
        workflows.execute_dealer_order_cancel('WF-CANCEL-3', 'worker-1')
    finish.assert_not_called()


# --------------------------------------------------------------------------- #
# 路由注册
# --------------------------------------------------------------------------- #
def test_dealer_order_cancel_routes_registered():
    routes = {route.path: route for route in dealer_order_routes.router.routes}
    assert '/{order_no}/cancel-preview' in routes
    assert 'GET' in routes['/{order_no}/cancel-preview'].methods
    assert '/{order_no}/cancel' in routes
    assert 'POST' in routes['/{order_no}/cancel'].methods


def test_dealer_order_cancel_router_requires_review_permission():
    dependencies = getattr(dealer_order_routes.router, 'dependencies', [])
    assert dependencies, '经销商订单路由必须带 DEALER_ORDER_REVIEW 权限依赖'
