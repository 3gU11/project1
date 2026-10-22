"""Adapters connecting existing business commands to versioned workflow execution."""
import json
import uuid
from contextvars import ContextVar
from fastapi import BackgroundTasks
from sqlalchemy import text
from starlette.requests import Request
from database import get_engine

_replay = ContextVar('forward_entry_replay', default=None)
_submit = ContextVar('forward_entry_submit', default=False)

def replaying():
    return _replay.get() is not None

def submitting():
    return _submit.get()

def stable_order_id(fallback):
    return (_replay.get() or {}).get('order_id') or fallback


def ensure_forward_receipts():
    with get_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS workflow_business_receipts (
            instance_id BIGINT NOT NULL PRIMARY KEY,
            status VARCHAR(30) NOT NULL, result JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""))


def submit_entry(key, payload, user, request=None, business_id='', order_id='', origin=None):
    if replaying():
        return None
    from api.routes.workflows import ReverseCreateRequest, ReverseItem, submit_reverse_instance
    data = payload.model_dump(mode='json')
    bid = business_id or order_id or ('BATCH-' + uuid.uuid4().hex[:16].upper())
    serials = sorted(set(data.get('serial_nos') or data.get('selected_serial_nos') or
                         ([data['serial_no']] if data.get('serial_no') else [])))
    contract_ids = ([data['contract_no']] if origin and data.get('contract_no') else []) or sorted({str(row.get('合同号') or '').strip() for row in data.get('rows', [])})
    objects = ([ReverseItem(object_type='机台', object_id=sn) for sn in serials] or
               [ReverseItem(object_type='新建合同', object_id=cid) for cid in contract_ids] or
               [ReverseItem(object_type='业务指令', object_id=bid)])
    idem = str(request.headers.get('X-Request-ID') or '') if request else ''
    token = _submit.set(True)
    try:
        response = submit_reverse_instance(ReverseCreateRequest(
            workflow_key=key, business_type='业务指令', business_id=bid,
            idempotency_key=f"entry:{key}:{user['username']}:{idem or uuid.uuid4().hex}",
            execution_data={'payload': data, 'order_id': order_id, 'origin': origin}, items=objects), user)
    finally:
        _submit.reset(token)
    row = response['data']
    result = row.get('business_result') or {}
    pending = row['status'] != '已完成'
    return {**result, 'workflow_status': row['status'], 'instance_no': row['instance_no'],
            'approval_pending': pending,
            'message': ('审批已发起，审批通过后自动执行' if row['status']=='审批中' else
                        result.get('message', '操作完成'))}


def _invoke(key, data, user):
    from api.routes import planning, inventory
    request = Request({'type': 'http', 'headers': []})
    operator = user.get('name') or user['username']
    raw = data['payload']
    if key == 'contract-create':
        tasks = BackgroundTasks()
        if data.get('origin'):
            from api.routes.dealer_orders import convert_to_contract, ConvertToContractPayload
            result = convert_to_contract(data['origin']['dealer_order_no'], ConvertToContractPayload.model_validate(raw), request, tasks, user)
        else:
            result = planning.create_contracts_batch(planning.BatchContractCreatePayload.model_validate(raw), request, tasks, operator, user)
        # The saved contract is authoritative; sandbox refresh is a follow-up.
        for task in tasks.tasks:
            try:
                task.func(*task.args, **task.kwargs)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Contract saved but follow-up refresh failed")
        return result
    if key == 'order-create':
        return planning.create_sales_order_api(planning.SalesOrderCreatePayload.model_validate(raw), request, operator, user)
    if key == 'allocation-create':
        return planning.allocate_order_inventory_api(data['business_id'], planning.OrderAllocatePayload.model_validate(raw), request, operator, user)
    if key in {'stock-inbound', 'stock-transfer'}:
        return inventory.inbound_machine_to_slot(inventory.InboundSlotPayload.model_validate(raw), request, user)
    if key == 'shipment-confirm':
        return inventory.confirm_shipping(inventory.ShippingActionPayload.model_validate(raw), request, operator, user)
    raise ValueError('未注册的正向业务流程')


def execute_forward_entry(instance_no, worker_id):
    from crud.workflows import _assert_lease_alive, _finish_reverse_execution, _validate_machine_snapshots
    from sqlalchemy import bindparam
    with get_engine().begin() as conn:
        row = conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE'), {'no': instance_no}).mappings().first()
        if not row or row['status'] != '执行中':
            raise ValueError('业务流程当前不可执行')
        instance = dict(row)
        lease = conn.execute(text("SELECT * FROM workflow_execution_attempts WHERE instance_id=:id AND worker_id=:worker AND status='执行中' ORDER BY id DESC LIMIT 1 FOR UPDATE"), {'id': row['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在')
        lease = dict(lease)
        _assert_lease_alive(conn, lease)
        receipt = conn.execute(text('SELECT * FROM workflow_business_receipts WHERE instance_id=:id FOR UPDATE'), {'id': row['id']}).mappings().first()
        if receipt:
            if receipt['status'] != '成功':
                raise ValueError('上次业务执行未确认完成，为避免重复操作，请先核查业务结果后处理；不会自动重复执行')
            result = receipt['result']
            result = json.loads(result) if isinstance(result,str) else result
            _finish_reverse_execution(conn, instance, lease, worker_id, result, force_reinbound=False)
            return {'instance_no': instance_no, 'status': '已完成', 'business_result': result}
        raw = row['target_state_snapshot']
        data = json.loads(raw) if isinstance(raw,str) else dict(raw)
        data['business_id'] = row['business_id']
        machine_items = conn.execute(text("SELECT * FROM workflow_instance_items WHERE instance_id=:id AND object_type='机台'"), {'id': row['id']}).mappings().all()
        if machine_items:
            sns = [x['object_id'] for x in machine_items]
            machines = conn.execute(text('SELECT * FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE').bindparams(bindparam('sns',expanding=True)), {'sns': sns}).mappings().all()
            _validate_machine_snapshots(machine_items,{str(m['流水号']).strip(): m for m in machines})
        user = conn.execute(text('SELECT username,name,role,status FROM users WHERE username=:u'), {'u':row['initiator_id']}).mappings().first()
        if not user or str(user['status']).lower() != 'active':
            raise ValueError('发起账号已停用，不能执行业务')
        user = dict(user)
        conn.execute(text("INSERT INTO workflow_business_receipts(instance_id,status) VALUES (:id,'执行中')"), {'id': row['id']})
    token = _replay.set(data)
    try:
        result = _invoke(instance['workflow_key'],data,user)
        if not isinstance(result,dict) or result.get('ok') is False:
            raise ValueError('业务执行未成功')
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE workflow_business_receipts SET status='成功',result=:result,completed_at=CURRENT_TIMESTAMP WHERE instance_id=:id"), {'id':instance['id'],'result':json.dumps(result,ensure_ascii=False,default=str)})
        with get_engine().begin() as conn:
            _finish_reverse_execution(conn,instance,lease,worker_id,result,force_reinbound=False)
        return {'instance_no':instance_no,'status':'已完成','business_result':result}
    finally:
        _replay.reset(token)
