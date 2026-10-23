from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from database import get_engine

from api.routes.auth import get_current_user_context, require_roles
from crud.workflows import (ensure_workflow_tables, list_instances, list_models, list_tasks, list_workflow_versions, save_workflow_draft,
                            create_reverse_instance, transition_reverse_instance,
                            list_derived_tasks, complete_derived_task, list_notifications, mark_notification_read,
                            acquire_execution_lease, execute_allocation_recall,
                            execute_shipment_recall, execute_customer_finished_recall, execute_customer_order_shipped, execute_customer_machine_plan,
                            create_and_execute_shipment_recall,
                            mark_execution_failure, execute_order_delete,
                            execute_model_dict_delete, claim_outbox_events,
                            complete_outbox_event, fail_outbox_event,
                            execute_contract_cancel, transfer_reverse_approval,
                            requeue_outbox_event, reclaim_expired_execution_leases, publish_workflow_model)
from crud.workflows import REVERSE_WORKFLOW_RULES
from crud.workflows import workflow_action_for_instance, dispatch_pending_model_notifications

router = APIRouter()


class ReverseItem(BaseModel):
    object_type: str
    object_id: str
    before_state: dict | None = None
    row_version: int | None = None


class ReverseCreateRequest(BaseModel):
    workflow_key: str
    business_type: str
    business_id: str
    idempotency_key: str = Field(min_length=1, max_length=180)
    reason: str = ''
    assignee_id: str = ''
    execution_data: dict | None = None
    items: list[ReverseItem] = Field(default_factory=list)


class WorkflowActionRequest(BaseModel):
    reason: str = ''

class WorkflowPublishRequest(BaseModel):
    snapshot: dict


class DerivedTaskCompleteRequest(BaseModel):
    reason: str = ''


class NotificationReadRequest(BaseModel):
    notification_id: int


@router.get('/models')
def get_workflow_models(
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _ctx: dict = Depends(get_current_user_context),
):
    return {'data': list_models(direction=direction, status=status), 'rules': REVERSE_WORKFLOW_RULES, 'runtime': {
        'forward_enabled': True,
        'reverse_submission_enabled': True,
        'reverse_execution_enabled': True,
    }}

@router.get('/models/{workflow_key}/versions')
def get_workflow_versions(workflow_key: str, _ctx: dict = Depends(get_current_user_context)):
    return {'data': list_workflow_versions(workflow_key)}


@router.get('/instances')
def get_workflow_instances(
    status: str | None = Query(default=None),
    business_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _ctx: dict = Depends(get_current_user_context),
):
    return {'data': list_instances(status=status, business_id=business_id, limit=limit)}

@router.post('/models/{workflow_key}/publish')
def publish_model(workflow_key: str, payload: WorkflowPublishRequest, ctx: dict = Depends(require_roles('admin', 'boss'))):
    try:
        return {'data': publish_workflow_model(workflow_key, payload.snapshot, ctx['username'])}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.post('/models/{workflow_key}/draft')
def save_model_draft(workflow_key: str, payload: WorkflowPublishRequest, ctx: dict = Depends(require_roles('admin', 'boss'))):
    try:
        return {'data': save_workflow_draft(workflow_key, payload.snapshot, ctx['username'])}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get('/tasks')
def get_workflow_tasks(
    status: str | None = Query(default=None),
    assignee_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _ctx: dict = Depends(get_current_user_context),
):
    return {'data': list_tasks(status=status, assignee_id=assignee_id, limit=limit)}


@router.get('/my-pending-count')
def get_my_pending_count(ctx: dict = Depends(get_current_user_context)):
    """Return the number of approval tasks currently assigned to the user."""
    ensure_workflow_tables()
    from database import get_engine
    with get_engine().connect() as conn:
        count = conn.execute(text("""SELECT COUNT(*) FROM workflow_tasks
            WHERE assignee_id=:assignee AND status='待处理'"""),
            {'assignee': str(ctx.get('username') or '').strip()}).scalar()
    return {'count': int(count or 0)}


@router.get('/derived-tasks')
def get_derived_tasks(status: str | None = Query(default='待处理'), limit: int = Query(default=100, ge=1, le=500), ctx: dict = Depends(get_current_user_context)):
    role = str(ctx.get('role') or '').strip().lower()
    if role not in {'inbound', 'admin', 'boss'}:
        raise HTTPException(status_code=403, detail='仅入库员可以处理重入库任务')
    return {'data': list_derived_tasks(status=status, assignee_id=None if role in {'admin', 'boss'} else ctx.get('username'), limit=limit)}


@router.get('/derived-tasks/pending-count')
def get_derived_pending_count(ctx: dict = Depends(get_current_user_context)):
    role = str(ctx.get('role') or '').strip().lower()
    if role not in {'inbound', 'admin', 'boss'}:
        return {'count': 0}
    return {'count': len(list_derived_tasks(status='待处理', assignee_id=None if role in {'admin', 'boss'} else ctx.get('username'), limit=500))}


@router.get('/notifications')
def get_workflow_notifications(unread_only: bool = Query(default=True), limit: int = Query(default=100, ge=1, le=500), ctx: dict = Depends(get_current_user_context)):
    return {'data': list_notifications(ctx.get('username'), unread_only=unread_only, limit=limit)}


@router.post('/notifications/read')
def read_workflow_notification(payload: NotificationReadRequest, ctx: dict = Depends(get_current_user_context)):
    try:
        return {'data': mark_notification_read(payload.notification_id, ctx.get('username'))}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/derived-tasks/{task_no}/complete')
def complete_derived_task_route(task_no: str, payload: DerivedTaskCompleteRequest, ctx: dict = Depends(get_current_user_context)):
    try:
        if str(ctx.get('role') or '').strip().lower() not in {'inbound', 'admin', 'boss'}:
            raise ValueError('仅入库员可以完成重入库任务')
        return {'data': complete_derived_task(task_no, ctx['username'], payload.reason)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/reverse/instances')
def submit_reverse_instance(payload: ReverseCreateRequest,
                            ctx: dict = Depends(get_current_user_context)):
    auto_execution_started = False
    try:
        from crud.workflows import FORWARD_ENTRY_ACTIONS
        from crud.forward_entries import submitting
        if payload.workflow_key in FORWARD_ENTRY_ACTIONS and not submitting():
            raise ValueError('请从对应业务页面发起此流程')
        # 发货撤回只允许在「待发货」阶段做（走 allocation-recall）。
        # 机台一旦已出库/已发货，就只能走退换货处理，不能再撤回。
        if payload.workflow_key == 'shipment-recall':
            raise ValueError('已发货的机台不能撤回，请到「发货复核 → 退换货处理」办理退回')
        if payload.workflow_key in {'order-delete', 'contract-cancel'}:
            column = '占用订单号' if payload.workflow_key == 'order-delete' else '合同号'
            operation = '订单删除' if payload.workflow_key == 'order-delete' else '合同取消'
            with get_engine().connect() as conn:
                shipped_rows = conn.execute(text(f"""SELECT `流水号`, `状态`
                    FROM finished_goods_data
                    WHERE TRIM(COALESCE(`{column}`,''))=:order_id
                      AND TRIM(COALESCE(`状态`,'')) IN ('已出库','已发货','库存中（DG-WH）')
                    ORDER BY `流水号`"""), {'order_id': str(payload.business_id).strip()}).mappings().all()
            if shipped_rows:
                details = '、'.join(f"{row['流水号']}（{row['状态']}）" for row in shipped_rows[:10])
                suffix = '等' if len(shipped_rows) > 10 else ''
                raise ValueError(f'存在已出库/已发货机台，不能发起{operation}：{details}{suffix}')
        row, created = create_reverse_instance(
            workflow_key=payload.workflow_key,
            execution_data=payload.execution_data,
            business_type=payload.business_type,
            business_id=payload.business_id,
            operator_id=ctx['username'],
            initiator_role=ctx.get('role', ''),
            idempotency_key=payload.idempotency_key,
            reason=payload.reason,
            assignee_id=payload.assignee_id,
            items=[item.model_dump() for item in payload.items] or None,
        )
        execution_result = None
        if row.get('status') in {'已通过', '执行异常', '重试中'}:
            acquire_execution_lease(row['instance_no'], ctx['username'])
            auto_execution_started = True
            action = workflow_action_for_instance(row['instance_no'])
            executors = {
                'recall_allocation': execute_allocation_recall,
                'recall_shipment': execute_shipment_recall,
                'recall_customer_finished': execute_customer_finished_recall,
                'ship_customer_order': execute_customer_order_shipped,
        'save_customer_machine_plan': execute_customer_machine_plan,
                'delete_order': execute_order_delete,
                'delete_order_reinbound': execute_order_delete,
                'disable_model': execute_model_dict_delete,
                'cancel_contract': execute_contract_cancel,
                'cancel_contract_reinbound': execute_contract_cancel,
                'create_shipment_recall': create_and_execute_shipment_recall,
            }
            from crud.forward_entries import execute_forward_entry
            from crud.workflows import FORWARD_ENTRY_ACTIONS
            executors.update({a: execute_forward_entry for a in FORWARD_ENTRY_ACTIONS.values()})
            execution_result = executors[action](row['instance_no'], ctx['username'])
            try:
                dispatch_pending_model_notifications(row['instance_no'])
            except Exception:
                import logging
                logging.getLogger(__name__).exception('automatic shipment recall succeeded but model notification delivery failed')
                execution_result = {**execution_result, 'notification_delivery_pending': True}
            row = {**row, **execution_result}
        return {'data': row, 'created': created}
    except ValueError as exc:
        if auto_execution_started:
            mark_execution_failure(row['instance_no'], ctx.get('username', ''), str(exc))
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        # Keep the client-facing error actionable; the server log still contains the full traceback.
        import logging
        logging.getLogger(__name__).exception('reverse workflow submission failed')
        if auto_execution_started:
            mark_execution_failure(row['instance_no'], ctx.get('username', ''), str(exc))
        raise HTTPException(status_code=500, detail=f'逆向流程提交失败：{exc}')


def _execute_approved_workflow(instance_no: str, operator_id: str):
    """Execute an approved workflow immediately; approval is the confirmation."""
    acquire_execution_lease(instance_no, operator_id)
    action = workflow_action_for_instance(instance_no)
    from crud.forward_entries import execute_forward_entry
    from crud.workflows import FORWARD_ENTRY_ACTIONS
    action_executor = {
        **{a: execute_forward_entry for a in FORWARD_ENTRY_ACTIONS.values()},
        'recall_allocation': execute_allocation_recall,
        'recall_shipment': execute_shipment_recall,
        'recall_customer_finished': execute_customer_finished_recall,
                'ship_customer_order': execute_customer_order_shipped,
        'save_customer_machine_plan': execute_customer_machine_plan,
        'delete_order': execute_order_delete,
        'delete_order_reinbound': execute_order_delete,
        'disable_model': execute_model_dict_delete,
        'cancel_contract': execute_contract_cancel,
        'cancel_contract_reinbound': execute_contract_cancel,
        'create_shipment_recall': create_and_execute_shipment_recall,
    }[action]
    result = action_executor(instance_no, operator_id)
    try:
        dispatch_pending_model_notifications(instance_no)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('workflow business action succeeded but model notification delivery failed')
        result = {**result, 'notification_delivery_pending': True}
    return result


@router.post('/instances/{instance_no}/approve')
def approve_workflow(instance_no: str, payload: WorkflowActionRequest,
                     ctx: dict = Depends(get_current_user_context)):
    try:
        approved = transition_reverse_instance(instance_no, 'approve', ctx['username'], payload.reason)
        execution_result = None
        if approved.get('status') == '已通过':
            try:
                execution_result = _execute_approved_workflow(instance_no, ctx['username'])
                approved = {**approved, **execution_result}
            except ValueError as exc:
                mark_execution_failure(instance_no, ctx['username'], str(exc))
                raise
            except Exception as exc:
                mark_execution_failure(instance_no, ctx['username'], str(exc))
                raise
        return {'data': approved}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/instances/{instance_no}/reject')
def reject_workflow(instance_no: str, payload: WorkflowActionRequest,
                    ctx: dict = Depends(get_current_user_context)):
    try:
        return {'data': transition_reverse_instance(instance_no, 'reject', ctx['username'], payload.reason)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/instances/{instance_no}/transfer')
def transfer_workflow(instance_no: str, payload: WorkflowActionRequest,
                      assignee_id: str = Query(..., min_length=1),
                      ctx: dict = Depends(get_current_user_context)):
    try:
        return {'data': transfer_reverse_approval(instance_no, ctx['username'], assignee_id, payload.reason)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/instances/{instance_no}/withdraw')
def withdraw_workflow(instance_no: str, payload: WorkflowActionRequest,
                      ctx: dict = Depends(get_current_user_context)):
    try:
        return {'data': transition_reverse_instance(instance_no, 'withdraw', ctx['username'], payload.reason)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/instances/{instance_no}/lease')
def lease_workflow(instance_no: str, ctx: dict = Depends(require_roles('admin', 'boss'))):
    try:
        return {'data': acquire_execution_lease(instance_no, ctx['username'])}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/instances/{instance_no}/execute')
def execute_workflow(instance_no: str, ctx: dict = Depends(require_roles('admin', 'boss'))):
    try:
        # A retry after an expired lease must reacquire execution ownership.
        with get_engine().connect() as conn:
            status = conn.execute(text('SELECT status FROM workflow_instances WHERE instance_no=:no'), {'no': instance_no}).scalar()
        if status in {'已通过', '执行异常', '重试中'}:
            acquire_execution_lease(instance_no, ctx['username'])
        action = workflow_action_for_instance(instance_no)
        from crud.forward_entries import execute_forward_entry
        from crud.workflows import FORWARD_ENTRY_ACTIONS
        action_executor = {
            **{a: execute_forward_entry for a in FORWARD_ENTRY_ACTIONS.values()},
            'recall_allocation': execute_allocation_recall,
            'recall_shipment': execute_shipment_recall,
            'recall_customer_finished': execute_customer_finished_recall,
                'ship_customer_order': execute_customer_order_shipped,
        'save_customer_machine_plan': execute_customer_machine_plan,
            'delete_order': execute_order_delete,
            'delete_order_reinbound': execute_order_delete,
            'disable_model': execute_model_dict_delete,
            'cancel_contract': execute_contract_cancel,
            'cancel_contract_reinbound': execute_contract_cancel,
        }[action]
        result = action_executor(instance_no, ctx['username'])
        try:
            dispatch_pending_model_notifications(instance_no)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('workflow business action succeeded but model notification delivery failed')
            result = {**result, 'notification_delivery_pending': True}
        return {'data': result}
    except ValueError as exc:
        mark_execution_failure(instance_no, ctx['username'], str(exc))
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        mark_execution_failure(instance_no, ctx['username'], str(exc))
        raise HTTPException(status_code=500, detail='逆向流程执行异常，已记录并可重试')


@router.post('/instances/{instance_no}/notifications/retry')
def retry_workflow_notifications(instance_no: str, _ctx: dict = Depends(require_roles('admin', 'boss'))):
    try:
        return {'data': {'sent_to': dispatch_pending_model_notifications(instance_no)}}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        import logging
        logging.getLogger(__name__).exception('workflow model notification retry failed')
        raise HTTPException(status_code=500, detail='通知发送失败，可稍后重试')


@router.get('/health')
def workflow_health(_ctx: dict = Depends(get_current_user_context)):
    ensure_workflow_tables()
    return {'status': 'ok', 'phase': 2, 'forward_enabled': True,
            'reverse_submission_enabled': True, 'reverse_execution_enabled': True}


@router.post('/admin/ensure-tables')
def ensure_tables(_ctx: dict = Depends(require_roles('admin', 'boss'))):
    ensure_workflow_tables()
    return {'message': '工作流基础表已就绪'}


@router.post('/admin/outbox/claim')
def claim_workflow_outbox(limit: int = Query(default=20, ge=1, le=100),
                          ctx: dict = Depends(require_roles('admin', 'boss'))):
    return {'data': claim_outbox_events(ctx['username'], limit)}


@router.post('/admin/outbox/{event_id}/complete')
def complete_workflow_outbox(event_id: int, _ctx: dict = Depends(require_roles('admin', 'boss'))):
    complete_outbox_event(event_id)
    return {'status': 'ok'}


@router.post('/admin/outbox/{event_id}/fail')
def fail_workflow_outbox(event_id: int, reason: str = Query(default='处理失败'),
                        _ctx: dict = Depends(require_roles('admin', 'boss'))):
    fail_outbox_event(event_id, reason)
    return {'status': 'ok'}


@router.post('/admin/outbox/{event_id}/requeue')
def requeue_workflow_outbox(event_id: int, _ctx: dict = Depends(require_roles('admin', 'boss'))):
    try:
        requeue_outbox_event(event_id)
        return {'status': 'ok'}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post('/admin/execution-leases/reclaim')
def reclaim_workflow_leases(limit: int = Query(default=100, ge=1, le=500),
                            _ctx: dict = Depends(require_roles('admin', 'boss'))):
    return {'data': reclaim_expired_execution_leases(limit)}


class PersonalMessageRead(BaseModel):
    message_key: str = Field(min_length=1, max_length=180)


@router.get('/personal-messages')
def personal_messages(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                      unread: bool = False, ctx: dict = Depends(get_current_user_context)):
    from crud.personal_messages import inbox
    return inbox(ctx['username'], page, limit, unread)


@router.post('/personal-messages/read')
def personal_message_read(payload: PersonalMessageRead, ctx: dict = Depends(get_current_user_context)):
    from crud.personal_messages import read_messages
    read_messages(ctx['username'], payload.message_key)
    return {'ok': True}


@router.post('/personal-messages/read-all')
def personal_messages_read_all(ctx: dict = Depends(get_current_user_context)):
    from crud.personal_messages import read_messages
    read_messages(ctx['username'])
    return {'ok': True}


@router.get('/configuration-options')
def workflow_configuration_options(ctx: dict = Depends(require_roles('admin', 'boss'))):
    # Model editors need assignment choices, not access to user administration.
    from crud.roles import list_roles
    with get_engine().connect() as conn:
        users = conn.execute(text("SELECT username,name,role FROM users WHERE status='active' ORDER BY username")).mappings().all()
    roles = list_roles()
    return {'users': [dict(row) for row in users],
            'roles': [{'role_id': row['role_id'], 'role_name': row['role_name']} for row in roles]}
