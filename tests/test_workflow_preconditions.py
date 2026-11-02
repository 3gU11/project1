"""流程前置校验的单元测试：注定失败的提交不能先建实例。

覆盖 2026-11-02 端到端测试暴露的三类场景：
1. 撤回配货把明细传成订单 → 必须直接拒绝（不建实例）；
2. 客户成品核销撤回时状态不满足 → 必须直接拒绝（不建实例）；
3. 发货确认未选机台 → 必须 422（不建实例）；
4. 库位转移目标已满 → 必须 422（不建实例）。
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text

from api.routes import inventory as inv_routes
from api.routes import workflows as wf_routes
from api.routes.workflows import ReverseCreateRequest, ReverseItem


def _engine_with_machines(rows):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE finished_goods_data (`流水号` TEXT, `状态` TEXT, `Location_Code` TEXT)"
        ))
        for serial_no, status, location in rows:
            conn.execute(
                text("INSERT INTO finished_goods_data VALUES (:sn, :st, :loc)"),
                {"sn": serial_no, "st": status, "loc": location},
            )
    return engine


def _reverse_payload(workflow_key, items, business_id="SO-1"):
    return ReverseCreateRequest(
        workflow_key=workflow_key,
        business_type="订单",
        business_id=business_id,
        idempotency_key=f"test-{workflow_key}",
        items=items,
    )


def test_allocation_recall_rejects_order_level_items():
    payload = _reverse_payload(
        "allocation-recall", [ReverseItem(object_type="订单", object_id="SO-1")]
    )
    with pytest.raises(ValueError) as error:
        wf_routes._assert_reverse_precondition(payload)
    assert "机台" in str(error.value)


def test_allocation_recall_accepts_machine_items():
    payload = _reverse_payload(
        "allocation-recall", [ReverseItem(object_type="机台", object_id="96-01-001")]
    )
    wf_routes._assert_reverse_precondition(payload)  # 不应抛错


def test_customer_finished_recall_rejects_unshipped_machine(monkeypatch):
    engine = _engine_with_machines([("96-01-001", "待入库", "")])
    monkeypatch.setattr(wf_routes, "get_engine", lambda: engine)
    payload = _reverse_payload(
        "customer-finished-recall", [ReverseItem(object_type="机台", object_id="96-01-001")]
    )
    with pytest.raises(ValueError) as error:
        wf_routes._assert_reverse_precondition(payload)
    assert "不可撤回" in str(error.value)


def test_customer_finished_recall_accepts_dongguan_warehouse_stock(monkeypatch):
    engine = _engine_with_machines([("96-01-002", "库存中（DG-WH）", "DG-WH")])
    monkeypatch.setattr(wf_routes, "get_engine", lambda: engine)
    payload = _reverse_payload(
        "customer-finished-recall", [ReverseItem(object_type="机台", object_id="96-01-002")]
    )
    wf_routes._assert_reverse_precondition(payload)  # 东莞仓在客户仓里，允许核销撤回


def test_customer_finished_recall_rejects_missing_machine(monkeypatch):
    engine = _engine_with_machines([])
    monkeypatch.setattr(wf_routes, "get_engine", lambda: engine)
    payload = _reverse_payload(
        "customer-finished-recall", [ReverseItem(object_type="机台", object_id="96-99-999")]
    )
    with pytest.raises(ValueError) as error:
        wf_routes._assert_reverse_precondition(payload)
    assert "不存在" in str(error.value)


def test_shipping_confirm_rejects_empty_serials_before_workflow(monkeypatch):
    """空机台列表必须在 submit_entry 之前被拦下，否则会留下随机 BATCH 号的实例。"""
    called = []
    monkeypatch.setattr(
        "crud.forward_entries.submit_entry",
        lambda *args, **kwargs: called.append(args) or None,
    )
    payload = inv_routes.ShippingActionPayload(serial_nos=[])
    with pytest.raises(HTTPException) as error:
        inv_routes.confirm_shipping_api(payload, None, current_operator="tester",
                                        current_user={"username": "tester"})
    assert error.value.status_code == 422
    assert called == []


def test_slot_capacity_precheck_blocks_full_slot(monkeypatch):
    engine = _engine_with_machines(
        [(f"96-02-00{i}", "库存中（C05）", "C05") for i in range(5)]
    )
    monkeypatch.setattr(inv_routes, "get_engine", lambda: engine)
    with pytest.raises(HTTPException) as error:
        inv_routes._assert_slot_has_room("96-02-009", "C05")
    assert error.value.status_code == 422
    assert "满载" in str(error.value.detail)


def test_slot_capacity_precheck_allows_slot_with_room(monkeypatch):
    engine = _engine_with_machines([("96-02-001", "库存中（C05）", "C05")])
    monkeypatch.setattr(inv_routes, "get_engine", lambda: engine)
    inv_routes._assert_slot_has_room("96-02-009", "C05")  # 1/5，不应抛错


def test_slot_capacity_precheck_skips_unlimited_slot(monkeypatch):
    engine = _engine_with_machines(
        [(f"96-03-00{i}", "库存中（老厂四车间一楼400）", "老厂四车间一楼400") for i in range(50)]
    )
    monkeypatch.setattr(inv_routes, "get_engine", lambda: engine)
    inv_routes._assert_slot_has_room("96-03-999", "老厂四车间一楼400")  # 不限容量，不应抛错


def _workflow_engine(status="执行异常"):
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _strip_locks(conn, cursor, statement, parameters, context, executemany):
        # sqlite 不支持 SELECT ... FOR UPDATE，测试里去掉行锁语法
        return statement.replace("FOR UPDATE", ""), parameters

    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE workflow_instances (
            id INTEGER PRIMARY KEY, instance_no TEXT, workflow_key TEXT, status TEXT,
            result TEXT, completed_at TEXT, initiator_id TEXT, model_version_id INTEGER)"""))
        conn.execute(text("""CREATE TABLE workflow_tasks (
            id INTEGER PRIMARY KEY, instance_id INTEGER, status TEXT, assignee_id TEXT,
            decision TEXT, completed_at TEXT)"""))
        conn.execute(text("""CREATE TABLE workflow_approval_records (
            id INTEGER PRIMARY KEY, instance_id INTEGER, task_id INTEGER, action TEXT,
            result TEXT, operator_id TEXT, reason TEXT, task_status_snapshot TEXT)"""))
        conn.execute(text("""CREATE TABLE workflow_audit_logs (
            id INTEGER PRIMARY KEY, instance_id INTEGER, action TEXT, operator_id TEXT,
            before_state TEXT, after_state TEXT, detail TEXT)"""))
        conn.execute(text("""CREATE TABLE workflow_object_locks (
            id INTEGER PRIMARY KEY, instance_id INTEGER, lock_status TEXT, released_at TEXT)"""))
        conn.execute(text("""CREATE TABLE workflow_instance_items (
            id INTEGER PRIMARY KEY, instance_id INTEGER, object_type TEXT, object_id TEXT,
            execution_result TEXT)"""))
        conn.execute(text("""INSERT INTO workflow_instances
            (id, instance_no, workflow_key, status, initiator_id, model_version_id)
            VALUES (1, 'WF-TEST-1', 'allocation-recall', :status, 'boss', 1)"""), {"status": status})
        conn.execute(text("INSERT INTO workflow_object_locks (id, instance_id, lock_status) VALUES (1, 1, '占用中')"))
        conn.execute(text("INSERT INTO workflow_instance_items (id, instance_id, object_type, object_id) VALUES (1, 1, '订单', 'SO-1')"))
    return engine


def test_abandon_releases_object_and_marks_items(monkeypatch):
    from crud import workflows as wf_crud

    engine = _workflow_engine()
    monkeypatch.setattr(wf_crud, "ensure_workflow_tables", lambda: None)
    monkeypatch.setattr(wf_crud, "get_engine", lambda: engine)

    row = wf_crud.transition_reverse_instance(
        "WF-TEST-1", "abandon", "boss", "参数传错，重新发起", operator_role="boss"
    )
    assert row["status"] == "已作废"
    with engine.connect() as conn:
        lock = conn.execute(text("SELECT lock_status FROM workflow_object_locks WHERE instance_id=1")).scalar()
        item = conn.execute(text("SELECT execution_result FROM workflow_instance_items WHERE instance_id=1")).scalar()
    assert lock == "已释放"
    assert item == "已作废"


def test_abandon_requires_admin_role(monkeypatch):
    from crud import workflows as wf_crud

    engine = _workflow_engine()
    monkeypatch.setattr(wf_crud, "ensure_workflow_tables", lambda: None)
    monkeypatch.setattr(wf_crud, "get_engine", lambda: engine)

    with pytest.raises(ValueError) as error:
        wf_crud.transition_reverse_instance("WF-TEST-1", "abandon", "sales", "想清理", operator_role="Sales")
    assert "管理员" in str(error.value)


def test_abandon_requires_reason(monkeypatch):
    from crud import workflows as wf_crud

    engine = _workflow_engine()
    monkeypatch.setattr(wf_crud, "ensure_workflow_tables", lambda: None)
    monkeypatch.setattr(wf_crud, "get_engine", lambda: engine)

    with pytest.raises(ValueError) as error:
        wf_crud.transition_reverse_instance("WF-TEST-1", "abandon", "boss", "  ", operator_role="boss")
    assert "原因" in str(error.value)


def test_abandon_only_applies_to_failed_instances(monkeypatch):
    from crud import workflows as wf_crud

    engine = _workflow_engine(status="已完成")
    monkeypatch.setattr(wf_crud, "ensure_workflow_tables", lambda: None)
    monkeypatch.setattr(wf_crud, "get_engine", lambda: engine)

    with pytest.raises(ValueError) as error:
        wf_crud.transition_reverse_instance("WF-TEST-1", "abandon", "boss", "清理", operator_role="boss")
    assert "不能执行该操作" in str(error.value)


# --- 东莞仓 / 已发货 判定口径统一 -------------------------------------------

def test_is_shipped_machine_covers_all_shipped_states():
    from crud.inventory import is_shipped_machine

    assert is_shipped_machine({"状态": "已出库"}) is True
    assert is_shipped_machine({"状态": "已发货"}) is True
    assert is_shipped_machine({"状态": "库存中（DG-WH）", "Location_Code": "DG-WH"}) is True
    assert is_shipped_machine({"状态": "库存中（DONGGUAN）", "Location_Code": "DONGGUAN"}) is True
    assert is_shipped_machine({"状态": "库存中（A01）", "Location_Code": "A01"}) is False
    assert is_shipped_machine({"状态": "待发货", "Location_Code": "A01"}) is False
    assert is_shipped_machine({}) is False


def test_shipped_machine_sql_matches_python_predicate():
    from crud.inventory import CUSTOMER_WAREHOUSE_LOCATIONS, shipped_machine_sql

    fragment = shipped_machine_sql("fg")
    assert "fg.`状态`" in fragment and "fg.`Location_Code`" in fragment
    for code in CUSTOMER_WAREHOUSE_LOCATIONS:
        assert code in fragment
    assert "已发货" in fragment and "已出库" in fragment


def test_customer_warehouse_location_sql_uses_all_three_codes():
    from crud.inventory import CUSTOMER_WAREHOUSE_LOCATIONS, customer_warehouse_location_sql

    fragment = customer_warehouse_location_sql("fg.`Location_Code`")
    for code in CUSTOMER_WAREHOUSE_LOCATIONS:
        assert code in fragment
