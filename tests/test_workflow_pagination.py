import pytest
from sqlalchemy import create_engine, text

from api.routes import workflows as workflow_routes
import crud.workflows as workflow_crud


@pytest.fixture
def workflow_engine(monkeypatch):
    """最小工作流实例表，用于验证分页 SQL 与可见范围过滤。"""
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('''CREATE TABLE workflow_instances (
            id INTEGER PRIMARY KEY, instance_no TEXT, workflow_key TEXT, business_type TEXT,
            business_id TEXT, status TEXT, initiator_id TEXT, result TEXT)'''))
        conn.execute(text('CREATE TABLE workflow_tasks (id INTEGER PRIMARY KEY, instance_id INTEGER, assignee_id TEXT)'))
        for index in range(1, 26):
            conn.execute(
                text('''INSERT INTO workflow_instances
                    (id, instance_no, workflow_key, business_type, business_id, status, initiator_id)
                    VALUES (:id, :no, 'order-create', '订单', :bid, :status, :initiator_id)'''),
                {
                    'id': index,
                    'no': f'WF-{index:03d}',
                    'bid': f'ORDER-{index}',
                    'status': '已完成' if index % 2 else '执行异常',
                    'initiator_id': 'alice' if index in (2, 7, 12) else 'bob',
                },
            )
        # alice 还作为 13 号实例的待办人，可见范围应为本人发起 ∪ 本人待办。
        conn.execute(text("INSERT INTO workflow_tasks (instance_id, assignee_id) VALUES (13, 'alice')"))
    monkeypatch.setattr(workflow_crud, 'get_engine', lambda: engine)
    monkeypatch.setattr(workflow_crud, 'ensure_workflow_tables', lambda: None)
    yield engine
    engine.dispose()


def test_instances_page_returns_exact_slice_with_total(workflow_engine):
    rows, total = workflow_crud.list_instances(limit=10, skip=0)
    assert total == 25
    assert len(rows) == 10
    assert [row['id'] for row in rows] == list(range(25, 15, -1))

    rows, total = workflow_crud.list_instances(limit=10, skip=20)
    assert total == 25
    assert [row['id'] for row in rows] == [5, 4, 3, 2, 1]

    # 超出末页时不报错，只返回空列表，总数仍为真实值。
    rows, total = workflow_crud.list_instances(limit=10, skip=30)
    assert total == 25
    assert rows == []


def test_instances_page_keeps_filters_and_visibility(workflow_engine):
    rows, total = workflow_crud.list_instances(limit=10, skip=0, status='失败')
    assert total == 12
    assert all(row['status'] == '执行异常' for row in rows)

    rows, total = workflow_crud.list_instances(limit=10, skip=0, visible_to='alice')
    assert total == 4
    assert {row['id'] for row in rows} == {2, 7, 12, 13}

    rows, total = workflow_crud.list_instances(limit=10, skip=0, visible_to='nobody')
    assert (total, rows) == (0, [])


def test_route_returns_total_alongside_page_rows(workflow_engine):
    body = workflow_routes.get_workflow_instances(
        status=None, business_id=None, skip=10, limit=10,
        ctx={'username': 'admin', 'role': 'admin'},
    )
    assert body['total'] == 25
    assert [row['id'] for row in body['data']] == list(range(15, 5, -1))

    # 非管理员走 SQL 可见范围过滤，分页总数同样只统计可见实例。
    body = workflow_routes.get_workflow_instances(
        status=None, business_id=None, skip=0, limit=10,
        ctx={'username': 'alice', 'role': 'sales'},
    )
    assert body['total'] == 4
    assert len(body['data']) == 4


def _seed_tasks(engine, total=25, alice_until=12):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM workflow_tasks'))
        for index in range(1, total + 1):
            conn.execute(
                text('INSERT INTO workflow_tasks (id, instance_id, assignee_id) VALUES (:id, :iid, :assignee)'),
                {'id': index, 'iid': index, 'assignee': 'alice' if index <= alice_until else 'bob'},
            )


def test_task_page_returns_exact_slice_with_total(workflow_engine):
    _seed_tasks(workflow_engine)

    rows, total = workflow_crud.list_tasks(limit=10, skip=0)
    assert total == 25
    assert len(rows) == 10
    assert [row['id'] for row in rows] == list(range(25, 15, -1))

    rows, total = workflow_crud.list_tasks(limit=10, skip=20)
    assert total == 25
    assert [row['id'] for row in rows] == [5, 4, 3, 2, 1]

    rows, total = workflow_crud.list_tasks(limit=10, skip=30)
    assert total == 25
    assert rows == []

    rows, total = workflow_crud.list_tasks(limit=10, skip=0, assignee_id='alice')
    assert total == 12
    assert all(row['assignee_id'] == 'alice' for row in rows)


def test_task_route_pages_and_restricts_non_admin(workflow_engine):
    _seed_tasks(workflow_engine)

    body = workflow_routes.get_workflow_tasks(
        status=None, assignee_id=None, skip=10, limit=10,
        ctx={'username': 'admin', 'role': 'boss'},
    )
    assert body['total'] == 25
    assert [row['id'] for row in body['data']] == list(range(15, 5, -1))

    # 非管理员即使传了别人的账号，也只能看到分派给自己的任务。
    body = workflow_routes.get_workflow_tasks(
        status=None, assignee_id='bob', skip=0, limit=10,
        ctx={'username': 'alice', 'role': 'sales'},
    )
    assert body['total'] == 12
    assert all(row['assignee_id'] == 'alice' for row in body['data'])
