"""第一阶段工作流基础设施：模型、版本、实例和任务的持久化。"""
import json
import math
import os
import uuid
from datetime import datetime
from sqlalchemy import text, bindparam
from database import get_engine


def ensure_workflow_tables() -> None:
    ddl = [
        """CREATE TABLE IF NOT EXISTS workflow_categories (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            category_key VARCHAR(80) NOT NULL,
            name VARCHAR(120) NOT NULL,
            description VARCHAR(500) DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_workflow_category_key (category_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_models (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            workflow_key VARCHAR(120) NOT NULL,
            name VARCHAR(160) NOT NULL,
            category_key VARCHAR(80) NOT NULL,
            direction VARCHAR(20) NOT NULL,
            processing_type VARCHAR(30) NOT NULL,
            business_object VARCHAR(80) NOT NULL,
            execution_scope VARCHAR(40) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT '草稿',
            is_required TINYINT(1) NOT NULL DEFAULT 0,
            current_version INT NOT NULL DEFAULT 0,
            created_by VARCHAR(100) DEFAULT '',
            updated_by VARCHAR(100) DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_workflow_model_key (workflow_key),
            KEY idx_workflow_model_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_model_versions (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            model_id BIGINT NOT NULL,
            version_no INT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT '草稿',
            trigger_config JSON NULL,
            precondition_config JSON NULL,
            target_state_config JSON NULL,
            node_snapshot JSON NULL,
            notification_config JSON NULL,
            runtime_enabled TINYINT(1) NOT NULL DEFAULT 0,
            published_by VARCHAR(100) DEFAULT '',
            published_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_workflow_model_version (model_id, version_no),
            KEY idx_workflow_version_status (model_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_instances (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_no VARCHAR(80) NOT NULL,
            workflow_key VARCHAR(120) NOT NULL,
            model_version_id BIGINT NOT NULL,
            request_id VARCHAR(120) DEFAULT '',
            batch_no VARCHAR(120) DEFAULT '',
            idempotency_key VARCHAR(180) NOT NULL,
            business_type VARCHAR(80) NOT NULL,
            business_id VARCHAR(120) NOT NULL,
            execution_scope_snapshot JSON NULL,
            before_state_snapshot JSON NULL,
            target_state_snapshot JSON NULL,
            status VARCHAR(30) NOT NULL,
            initiator_id VARCHAR(100) DEFAULT '',
            executor_id VARCHAR(100) DEFAULT '',
            result VARCHAR(30) DEFAULT '',
            failure_reason TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL,
            UNIQUE KEY uq_workflow_instance_no (instance_no),
            UNIQUE KEY uq_workflow_instance_idempotency (idempotency_key),
            KEY idx_workflow_instance_business (business_type, business_id),
            KEY idx_workflow_instance_batch (batch_no),
            KEY idx_workflow_instance_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_tasks (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NOT NULL,
            node_type VARCHAR(30) NOT NULL,
            node_order INT NOT NULL DEFAULT 0,
            assignee_id VARCHAR(100) DEFAULT '',
            status VARCHAR(30) NOT NULL,
            decision VARCHAR(30) DEFAULT '',
            comment TEXT,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL,
            KEY idx_workflow_task_instance (instance_id),
            KEY idx_workflow_task_assignee (assignee_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_attempts (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            request_id VARCHAR(120) DEFAULT '', batch_no VARCHAR(120) DEFAULT '',
            idempotency_key VARCHAR(180) NOT NULL, business_type VARCHAR(80) NOT NULL,
            business_id VARCHAR(120) NOT NULL, workflow_key VARCHAR(120) NOT NULL,
            attempt_no INT NOT NULL DEFAULT 1, stage VARCHAR(50) NOT NULL,
            error_code VARCHAR(80) DEFAULT '', error_message TEXT,
            operator_id VARCHAR(100) DEFAULT '', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_workflow_attempt_business (business_type, business_id),
            KEY idx_workflow_attempt_request (request_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_instance_items (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NOT NULL,
            object_type VARCHAR(80) NOT NULL,
            object_id VARCHAR(120) NOT NULL,
            before_state JSON NULL,
            row_version BIGINT NULL,
            updated_at_snapshot DATETIME(6) NULL,
            execution_result VARCHAR(30) DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_workflow_item (instance_id, object_type, object_id),
            KEY idx_workflow_item_object (object_type, object_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_approval_records (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NOT NULL,
            task_id BIGINT NULL,
            action VARCHAR(40) NOT NULL,
            result VARCHAR(40) DEFAULT '',
            operator_id VARCHAR(100) NOT NULL,
            reason TEXT,
            task_status_snapshot VARCHAR(30) DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_workflow_approval_instance (instance_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_audit_logs (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NULL,
            action VARCHAR(60) NOT NULL,
            operator_id VARCHAR(100) NOT NULL,
            before_state VARCHAR(40) DEFAULT '',
            after_state VARCHAR(40) DEFAULT '',
            detail JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_workflow_audit_instance (instance_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_object_locks (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NOT NULL,
            object_type VARCHAR(80) NOT NULL,
            object_id VARCHAR(120) NOT NULL,
            lock_status VARCHAR(20) NOT NULL DEFAULT '占用中',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            released_at DATETIME NULL,
            active_lock TINYINT GENERATED ALWAYS AS (CASE WHEN lock_status='占用中' THEN 1 ELSE NULL END) STORED,
            UNIQUE KEY uq_workflow_object_lock (object_type, object_id, active_lock),
            KEY idx_workflow_object_lock_instance (instance_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_execution_attempts (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NOT NULL,
            attempt_no INT NOT NULL,
            stage VARCHAR(40) NOT NULL,
            status VARCHAR(30) NOT NULL,
            worker_id VARCHAR(100) DEFAULT '',
            lease_token VARCHAR(120) DEFAULT '',
            lease_expires_at DATETIME(6) NULL,
            validation_result JSON NULL,
            failure_reason TEXT,
            operator_id VARCHAR(100) DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME(6) NULL,
            UNIQUE KEY uq_workflow_attempt_no (instance_id, attempt_no),
            KEY idx_workflow_attempt_lease (status, lease_expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_outbox_events (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            instance_id BIGINT NULL,
            event_type VARCHAR(60) NOT NULL,
            idempotency_key VARCHAR(220) NOT NULL,
            payload JSON NULL,
            status VARCHAR(30) NOT NULL DEFAULT '待发送',
            retry_count INT NOT NULL DEFAULT 0,
            next_retry_at DATETIME NULL,
            failure_reason TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_workflow_outbox_key (idempotency_key),
            KEY idx_workflow_outbox_status (status, next_retry_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_derived_tasks (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            task_no VARCHAR(100) NOT NULL,
            instance_id BIGINT NOT NULL,
            task_type VARCHAR(40) NOT NULL,
            object_id VARCHAR(120) NOT NULL,
            assignee_role VARCHAR(80) NOT NULL DEFAULT '入库员',
            assignee_id VARCHAR(100) DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT '待处理',
            before_state JSON NULL,
            target_state VARCHAR(40) DEFAULT '待入库',
            notification_status VARCHAR(30) NOT NULL DEFAULT '待通知',
            completed_by VARCHAR(100) DEFAULT '',
            completed_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_derived_task (instance_id, task_type, object_id),
            KEY idx_derived_task_assignee (assignee_id, status),
            KEY idx_derived_task_instance (instance_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS workflow_notifications (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            recipient_id VARCHAR(100) NOT NULL,
            notification_type VARCHAR(40) NOT NULL,
            reference_no VARCHAR(120) NOT NULL,
            title VARCHAR(200) NOT NULL,
            content TEXT,
            status VARCHAR(20) NOT NULL DEFAULT '未读',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            read_at DATETIME NULL,
            UNIQUE KEY uq_workflow_notification (recipient_id, notification_type, reference_no),
            KEY idx_workflow_notification_recipient (recipient_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    ]
    with get_engine().begin() as conn:
        for statement in ddl:
            conn.execute(text(statement))
        # Only active locks must be unique; released history can repeat.
        lock_columns = conn.execute(text("SHOW COLUMNS FROM workflow_object_locks LIKE 'active_lock'")).first()
        if not lock_columns:
            conn.execute(text("""ALTER TABLE workflow_object_locks
                DROP INDEX uq_workflow_object_lock,
                ADD COLUMN active_lock TINYINT GENERATED ALWAYS AS
                    (CASE WHEN lock_status='占用中' THEN 1 ELSE NULL END) STORED,
                ADD UNIQUE KEY uq_workflow_object_lock (object_type, object_id, active_lock)"""))


def seed_phase1_models() -> None:
    """写入第一阶段模型清单；仅首次写入，不启用逆向运行。"""
    models = [
        ('contract-create', '创建合同', '合同流程', '正向', '自动通过', '合同', '合同', 1),
        ('order-create', '创建销售订单', '订单流程', '正向', '自动通过', '订单', '整单', 1),
        ('allocation-create', '订单配货', '配货流程', '正向', '自动通过', '订单', '整单', 1),
        ('stock-inbound', '成品入库', '库存流程', '正向', '自动通过', '机台', '单机台', 1),
        ('stock-transfer', '库位转移', '库存流程', '正向', '自动通过', '机台', '单机台', 1),
        ('shipment-confirm', '发货确认', '发货流程', '正向', '自动通过', '发货单', '整单', 1),
        ('customer-machine-plan', '客户机台规划', '客户成品流程', '正向', '自动通过', '机台', '单机台', 0),
        ('customer-order-shipped', '客户成品订单已发货', '客户成品流程', '正向', '自动通过', '客户成品订单', '整单', 0),
        ('contract-cancel', '取消合同', '合同流程', '逆向', '需要审批', '合同', '整单', 0),
        ('model-dict-delete', '删除机型字典', '基础资料流程', '逆向', '需要审批', '机型字典', '基础资料对象', 0),
        ('order-delete', '删除订单', '订单流程', '逆向', '需要审批', '订单', '整单', 0),
        ('allocation-recall', '撤回配货', '配货流程', '逆向', '需要审批', '配货单', '整单', 0),
        ('shipment-recall', '发货撤回', '发货流程', '逆向', '自动通过', '发货单', '整单', 0),
        ('customer-finished-recall', '客户成品核销发货撤回', '客户成品流程', '逆向', '需要审批', '客户成品', '整单', 0),
    ]
    with get_engine().begin() as conn:
        for key, name, category, direction, processing, obj, scope, required in models:
            conn.execute(text("""INSERT INTO workflow_models
                (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,is_required,status)
                VALUES (:key,:name,:category,:direction,:processing,:object,:scope,:required,'已发布')
                ON DUPLICATE KEY UPDATE name=VALUES(name), category_key=VALUES(category_key),
                    processing_type=VALUES(processing_type)"""), {
                    'key': key, 'name': name, 'category': category, 'direction': direction,
                    'processing': processing, 'object': obj, 'scope': scope, 'required': required,
                })
        rows = conn.execute(text("SELECT id, workflow_key FROM workflow_models WHERE current_version=0")).mappings().all()
        for row in rows:
            conn.execute(text("""INSERT INTO workflow_model_versions
                (model_id,version_no,status,runtime_enabled,node_snapshot)
                VALUES (:model_id,1,'已发布',:runtime_enabled,:nodes)"""), {
                    'model_id': row['id'], 'runtime_enabled': 0,
                    'nodes': json.dumps({'phase': 1, 'runtime_enabled': False}, ensure_ascii=False),
                })
            conn.execute(text("UPDATE workflow_models SET current_version=1 WHERE id=:id"), {'id': row['id']})


def migrate_phase1_workflow_metadata() -> None:
    """完成工作流元数据迁移；可重复执行，不修改业务数据。"""
    ensure_workflow_tables()
    categories = [
        ('合同流程', '合同流程', '合同创建及后续动作'),
        ('订单流程', '订单流程', '销售订单创建及配货'),
        ('配货流程', '配货流程', '订单配货'),
        ('库存流程', '库存流程', '入库和库位转移'),
        ('发货流程', '发货流程', '发货确认'),
        ('客户成品流程', '客户成品流程', '客户成品及机台规划'),
        ('基础资料流程', '基础资料流程', '基础资料逆向操作'),
    ]
    with get_engine().begin() as conn:
        for key, name, description in categories:
            conn.execute(text("""INSERT INTO workflow_categories
                (category_key,name,description) VALUES (:key,:name,:description)
                ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description)"""),
                         {'key': key, 'name': name, 'description': description})
        conn.execute(text("""UPDATE workflow_model_versions v
            JOIN workflow_models m ON m.id=v.model_id
            SET v.runtime_enabled=1
            WHERE m.direction='正向' AND m.status='已发布' AND v.status='已发布'
              AND v.version_no=m.current_version"""))
        approval_rows = conn.execute(text("""SELECT v.id,v.node_snapshot FROM workflow_model_versions v
            JOIN workflow_models m ON m.id=v.model_id
            WHERE v.status='已发布' AND v.version_no=m.current_version
              AND m.direction='逆向'""")).mappings().all()
        for row in approval_rows:
            raw = row.get('node_snapshot')
            try:
                snapshot = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except (TypeError, ValueError):
                continue
            changed = False
            for node in snapshot.get('nodes', []) if isinstance(snapshot, dict) else []:
                if isinstance(node, dict) and str(node.get('type') or '').lower() in {'approval', 'approve'} and not node.get('approvalRoles'):
                    node['approvalRoles'] = ['Boss']
                    node.pop('assigneesText', None)
                    changed = True
            if changed:
                conn.execute(text("UPDATE workflow_model_versions SET node_snapshot=:snapshot WHERE id=:id"),
                             {'id': row['id'], 'snapshot': _json(snapshot)})
        action_by_key = {
            'allocation-recall': 'recall_allocation',
            'shipment-recall': 'recall_shipment',
            'customer-finished-recall': 'recall_customer_finished',
            'order-delete': 'delete_order',
            'model-dict-delete': 'disable_model',
            'contract-cancel': 'cancel_contract',
        }
        action_rows = conn.execute(text("""SELECT v.id,m.workflow_key,v.node_snapshot FROM workflow_model_versions v
            JOIN workflow_models m ON m.id=v.model_id
            WHERE v.status='已发布' AND v.version_no=m.current_version AND m.direction='逆向'""")).mappings().all()
        for row in action_rows:
            try:
                snapshot = json.loads(row['node_snapshot']) if isinstance(row['node_snapshot'], str) else (row['node_snapshot'] or {})
            except (TypeError, ValueError):
                continue
            changed = False
            for node in snapshot.get('nodes', []) if isinstance(snapshot, dict) else []:
                if isinstance(node, dict) and str(node.get('type') or '').lower() == 'execute' and not node.get('action'):
                    action = action_by_key.get(row['workflow_key'])
                    if action:
                        node['action'] = action
                        changed = True
            if changed:
                conn.execute(text("UPDATE workflow_model_versions SET node_snapshot=:snapshot WHERE id=:id"),
                             {'id': row['id'], 'snapshot': _json(snapshot)})
        # Existing phase-one snapshots for automatic shipment recalls were
        # created before the no-approval policy. Replace only the known
        # default graph; custom snapshots are left untouched.
        automatic_recall_keys = ('shipment-recall',)
        rows = conn.execute(text("""SELECT v.id, m.workflow_key, v.node_snapshot
            FROM workflow_model_versions v
            JOIN workflow_models m ON m.id=v.model_id
            WHERE m.workflow_key IN ('shipment-recall')
              AND v.status='已发布'""")).mappings().all()
        for row in rows:
            raw = row.get('node_snapshot')
            try:
                snapshot = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except (TypeError, ValueError):
                snapshot = {}
            nodes = snapshot.get('nodes') if isinstance(snapshot, dict) else None
            node_types = {str(node.get('type') or '') for node in nodes} if isinstance(nodes, list) else set()
            has_inbound_notify = any(
                isinstance(node, dict)
                and str(node.get('type') or '') == 'notify'
                and 'Inbound' in (node.get('notifyRoles') or [])
                for node in (nodes or [])
            )
            if node_types == {'start', 'execute', 'notify', 'end'} and has_inbound_notify:
                continue
            snapshot = {
                'nodes': [
                    {'id': 'start', 'type': 'start', 'label': '发起', 'x': 35, 'y': 120},
                    {'id': 'execute', 'type': 'execute', 'label': '自动执行', 'x': 220, 'y': 120, 'targetState': '按业务执行器处理'},
                    {'id': 'notify', 'type': 'notify', 'label': '通知', 'x': 405, 'y': 120, 'notifyRoles': ['Inbound']},
                    {'id': 'end', 'type': 'end', 'label': '结束', 'x': 590, 'y': 120},
                ],
                'edges': [
                    {'source': 'start', 'target': 'execute'},
                    {'source': 'execute', 'target': 'notify'},
                    {'source': 'notify', 'target': 'end'},
                ],
            }
            conn.execute(text("UPDATE workflow_model_versions SET node_snapshot=:snapshot WHERE id=:id"),
                         {'id': row['id'], 'snapshot': _json(snapshot)})
            conn.execute(text("UPDATE workflow_models SET processing_type='自动通过' WHERE workflow_key=:key"),
                         {'key': row['workflow_key']})



def _json(value):
    # Database snapshots contain DATETIME values; encode them consistently for JSON columns.
    return json.dumps(value or {}, ensure_ascii=False, separators=(',', ':'), default=lambda item: item.isoformat() if hasattr(item, 'isoformat') else str(item))


def list_models(direction: str | None = None, status: str | None = None):
    ensure_workflow_tables()
    clauses, params = [], {}
    if direction:
        clauses.append('direction=:direction'); params['direction'] = direction
    if status:
        clauses.append('status=:status'); params['status'] = status
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    with get_engine().begin() as conn:
        rows = conn.execute(text(f'''SELECT m.*, v.node_snapshot, d.node_snapshot AS draft_snapshot
            FROM workflow_models m
            LEFT JOIN workflow_model_versions v ON v.model_id=m.id
              AND v.version_no=m.current_version
            LEFT JOIN workflow_model_versions d ON d.model_id=m.id AND d.status='草稿'
            {where.replace('status=', 'm.status=') if where else ''}
            ORDER BY m.category_key, m.name'''), params).mappings().all()
    return [dict(row) for row in rows]

def list_workflow_versions(workflow_key: str):
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        rows = conn.execute(text("""SELECT v.version_no,v.status,v.node_snapshot,v.runtime_enabled,v.published_by,v.published_at
            FROM workflow_model_versions v JOIN workflow_models m ON m.id=v.model_id
            WHERE m.workflow_key=:key ORDER BY v.version_no DESC"""), {'key': workflow_key}).mappings().all()
    # Normalize database-native values before returning them through the API.
    # Some database drivers expose DATETIME as a Python datetime, which is not
    # serializable by the JSON response encoder used by this service.
    result = []
    for row in rows:
        item = dict(row)
        published_at = item.get('published_at')
        if published_at is not None and hasattr(published_at, 'isoformat'):
            item['published_at'] = published_at.isoformat(sep=' ', timespec='seconds')
        result.append(item)
    return result


def list_instances(status: str | None = None, business_id: str | None = None, limit: int = 100):
    ensure_workflow_tables()
    clauses, params = [], {'limit': max(1, min(int(limit), 500))}
    if status:
        # The UI exposes business-friendly groups while the table stores the
        # concrete lifecycle status for each execution stage.
        status_groups = {
            '处理中': ('审批中', '已通过', '执行中', '执行异常', '重试中', '永久失败待处理'),
            '失败': ('执行异常', '永久失败待处理'),
        }
        grouped = status_groups.get(status)
        if grouped:
            placeholders = ','.join(f':status_{index}' for index in range(len(grouped)))
            clauses.append(f'status IN ({placeholders})')
            params.update({f'status_{index}': value for index, value in enumerate(grouped)})
        else:
            clauses.append('status=:status'); params['status'] = status
    if business_id:
        clauses.append('business_id LIKE :business_id'); params['business_id'] = f'%{business_id.strip()}%'
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    with get_engine().begin() as conn:
        rows = conn.execute(text(f'SELECT * FROM workflow_instances{where} ORDER BY id DESC LIMIT :limit'), params).mappings().all()
    return [dict(row) for row in rows]


def list_tasks(status: str | None = None, assignee_id: str | None = None, limit: int = 100):
    ensure_workflow_tables()
    clauses, params = [], {'limit': max(1, min(int(limit), 500))}
    if status:
        clauses.append('status=:status'); params['status'] = status
    if assignee_id:
        clauses.append('assignee_id=:assignee_id'); params['assignee_id'] = assignee_id
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    with get_engine().begin() as conn:
        rows = conn.execute(text(f'SELECT * FROM workflow_tasks{where} ORDER BY id DESC LIMIT :limit'), params).mappings().all()
    return [dict(row) for row in rows]


def list_derived_tasks(status: str | None = None, assignee_id: str | None = None, limit: int = 100):
    ensure_workflow_tables()
    clauses, params = [], {'limit': max(1, min(int(limit), 500))}
    if status:
        clauses.append('status=:status'); params['status'] = status
    if assignee_id:
        clauses.append('''(assignee_id=:assignee OR assignee_id='' OR EXISTS (
            SELECT 1 FROM users u WHERE u.username=:assignee
              AND LOWER(TRIM(CONVERT(u.role USING utf8mb4))) COLLATE utf8mb4_general_ci='inbound'
              AND LOWER(TRIM(CONVERT(COALESCE(u.status,'') USING utf8mb4))) COLLATE utf8mb4_general_ci='active'))''')
        params['assignee'] = assignee_id
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    with get_engine().begin() as conn:
        rows = conn.execute(text(f'''SELECT d.*, i.instance_no AS source_instance_no, i.workflow_key
            FROM workflow_derived_tasks d JOIN workflow_instances i ON i.id=d.instance_id
            {where.replace('status=', 'd.status=').replace('assignee_id=', 'd.assignee_id=')} ORDER BY d.id DESC LIMIT :limit'''), params).mappings().all()
    return [dict(row) for row in rows]


def complete_reinbound_tasks_for_machine(conn, serial_no: str, operator_id: str):
    """Close pending requirements satisfied by this actual inbound transaction."""
    tasks = conn.execute(text("""SELECT id,instance_id,task_no FROM workflow_derived_tasks
        WHERE object_id=:sn AND task_type='重入库' AND status='待处理' FOR UPDATE"""),
        {'sn': serial_no}).mappings().all()
    for task in tasks:
        conn.execute(text("""UPDATE workflow_derived_tasks SET status='已完成',
            completed_by=:operator,completed_at=CURRENT_TIMESTAMP,notification_status='已完成'
            WHERE id=:id AND status='待处理'"""), {'id': task['id'], 'operator': operator_id})
        conn.execute(text("""UPDATE workflow_notifications SET status='已读',read_at=CURRENT_TIMESTAMP
            WHERE reference_no=:no AND status='未读'"""), {'no': task['task_no']})
        conn.execute(text("""INSERT INTO workflow_audit_logs
            (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'重入库完成',:operator,'待处理','已完成',:detail)"""),
            {'id': task['instance_id'], 'operator': operator_id,
             'detail': _json({'task_no': task['task_no'], 'serial_no': serial_no})})
    for instance_id in {task['instance_id'] for task in tasks}:
        remaining = conn.execute(text("SELECT COUNT(*) FROM workflow_derived_tasks WHERE instance_id=:id AND status<>'已完成'"), {'id': instance_id}).scalar()
        if not remaining:
            conn.execute(text("UPDATE workflow_instances SET status='已完成',completed_at=CURRENT_TIMESTAMP WHERE id=:id AND status='待派生处理'"), {'id': instance_id})
    return len(tasks)


def complete_derived_task(task_no: str, operator_id: str, reason: str = ''):
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        task = conn.execute(text('SELECT * FROM workflow_derived_tasks WHERE task_no=:no FOR UPDATE'), {'no': task_no}).mappings().first()
        if not task:
            raise ValueError('派生任务不存在')
        if task['status'] == '已完成':
            return dict(task)
        if task['status'] != '待处理':
            raise ValueError(f"派生任务当前状态为{task['status']}，不能完成")
        row = conn.execute(text("SELECT `状态` FROM finished_goods_data WHERE TRIM(`流水号`)=:sn FOR UPDATE"), {'sn': task['object_id']}).mappings().first()
        if not row or not str(row.get('状态') or '').strip().startswith('库存中'):
            raise ValueError('机台尚未完成实际入库，不能关闭派生任务')
        conn.execute(text("""UPDATE workflow_derived_tasks SET status='已完成', completed_by=:operator,
            completed_at=CURRENT_TIMESTAMP, notification_status='已完成' WHERE id=:id AND status='待处理'"""),
            {'operator': operator_id, 'id': task['id']})
        remaining = conn.execute(text("SELECT COUNT(*) FROM workflow_derived_tasks WHERE instance_id=:id AND status<>'已完成'"), {'id': task['instance_id']}).scalar()
        if not remaining:
            conn.execute(text("UPDATE workflow_instances SET status='已完成', completed_at=CURRENT_TIMESTAMP WHERE id=:id AND status='待派生处理'"), {'id': task['instance_id']})
        return dict(conn.execute(text('SELECT * FROM workflow_derived_tasks WHERE id=:id'), {'id': task['id']}).mappings().first())


def list_notifications(recipient_id: str, unread_only: bool = True, limit: int = 100):
    ensure_workflow_tables()
    clause = "AND status='未读'" if unread_only else ''
    with get_engine().begin() as conn:
        rows = conn.execute(text(f"SELECT * FROM workflow_notifications WHERE recipient_id=:recipient {clause} ORDER BY id DESC LIMIT :limit"), {'recipient': recipient_id, 'limit': max(1, min(int(limit), 500))}).mappings().all()
    return [dict(row) for row in rows]


def mark_notification_read(notification_id: int, recipient_id: str):
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        changed = conn.execute(text("UPDATE workflow_notifications SET status='已读', read_at=CURRENT_TIMESTAMP WHERE id=:id AND recipient_id=:recipient AND status='未读'"), {'id': notification_id, 'recipient': recipient_id})
        if changed.rowcount != 1:
            raise ValueError('通知不存在或已读')
    return {'id': notification_id, 'status': '已读'}


FORWARD_ENTRY_ACTIONS = {
    'contract-create': 'create_contract', 'order-create': 'create_sales_order',
    'allocation-create': 'allocate_order', 'stock-inbound': 'inbound_machine',
    'stock-transfer': 'transfer_machine', 'shipment-confirm': 'confirm_shipment',
}

REVERSE_WORKFLOW_KEYS = set(FORWARD_ENTRY_ACTIONS) | {
    'customer-machine-plan',
    'customer-order-shipped',
    'contract-cancel', 'model-dict-delete', 'order-delete',
    'allocation-recall', 'shipment-recall', 'customer-finished-recall',
}

# Phase 1 business policy. Execution and derived-task creation are implemented
# in later phases; keeping the policy centralized prevents each executor from
# inventing its own approval semantics.
REVERSE_WORKFLOW_RULES = {
    'contract-cancel': {'approval': 'required', 'derived_task': 'conditional-reinbound'},
    'model-dict-delete': {'approval': 'required', 'derived_task': 'none'},
    'order-delete': {'approval': 'required', 'derived_task': 'conditional-reinbound'},
    'allocation-recall': {'approval': 'required', 'derived_task': 'conditional-reinbound'},
    'shipment-recall': {'approval': 'automatic', 'derived_task': 'conditional-reinbound'},
    # 发货撤回及客户成品核销撤回均自动通过；需要回库时只派生重入库通知。
    'customer-finished-recall': {'approval': 'required', 'derived_task': 'conditional-reinbound'},
}


def reverse_workflow_rule(workflow_key: str) -> dict:
    """Return the server-owned policy for a reverse workflow."""
    try:
        return dict(REVERSE_WORKFLOW_RULES[workflow_key])
    except KeyError:
        raise ValueError('不支持的逆向流程类型')


def create_reinbound_tasks(conn, instance: dict, operator_id: str = '', force: bool | None = None,
                           object_ids: list[str] | None = None) -> list[dict]:
    """Create idempotent reinbound tasks for machines returned to 待入库."""
    if force is False:
        return []
    rule = reverse_workflow_rule(str(instance.get('workflow_key') or ''))
    if rule.get('derived_task') != 'conditional-reinbound' or force is False:
        return []
    items = conn.execute(text("""SELECT object_id, before_state FROM workflow_instance_items
        WHERE instance_id=:id AND object_type IN ('机台','客户成品')"""), {'id': instance['id']}).mappings().all()
    if object_ids:
        items = [{'object_id': str(object_id).strip(), 'before_state': '{}'}
                 for object_id in object_ids if str(object_id).strip()]
    if not items and str(instance.get('business_type') or '') in ('订单', '销售订单', '合同'):
        column = '占用订单号' if str(instance.get('business_type') or '') != '合同' else '合同号'
        items = conn.execute(text(f"""SELECT `流水号` AS object_id, '{{}}' AS before_state
            FROM finished_goods_data WHERE TRIM(COALESCE(`{column}`,''))=TRIM(:business_id)
              AND TRIM(COALESCE(`状态`,''))='待入库'"""), {'business_id': instance.get('business_id')}).mappings().all()
    created = []
    assignee = conn.execute(text("""SELECT username FROM users
        WHERE LOWER(TRIM(CONVERT(role USING utf8mb4))) COLLATE utf8mb4_general_ci='inbound'
          AND LOWER(TRIM(CONVERT(COALESCE(status,'') USING utf8mb4))) COLLATE utf8mb4_general_ci='active'
        ORDER BY (SELECT COUNT(*) FROM workflow_derived_tasks d
                  WHERE CONVERT(d.assignee_id USING utf8mb4) COLLATE utf8mb4_general_ci =
                        CONVERT(users.username USING utf8mb4) COLLATE utf8mb4_general_ci
                    AND d.status='待处理'), username LIMIT 1""")).scalar()
    if not assignee:
        raise ValueError('系统没有可用的入库员账号，无法创建重入库任务')
    for item in items:
        current = conn.execute(text("SELECT `状态` FROM finished_goods_data WHERE TRIM(`流水号`)=:sn FOR UPDATE"), {'sn': item['object_id']}).mappings().first()
        if not current or str(current.get('状态') or '').strip() != '待入库':
            continue
        task_no = f"RI-{instance['instance_no']}-{str(item['object_id']).strip()}"
        conn.execute(text("""INSERT INTO workflow_derived_tasks
            (task_no,instance_id,task_type,object_id,before_state,target_state,notification_status)
            VALUES (:task_no,:instance,'重入库',:object_id,:before_state,'待入库','待通知')
            ON DUPLICATE KEY UPDATE task_no=VALUES(task_no), assignee_id=COALESCE(NULLIF(assignee_id,''), VALUES(assignee_id))"""), {
            'task_no': task_no, 'instance': instance['id'], 'object_id': str(item['object_id']).strip(),
            'before_state': item.get('before_state') or '{}',
            'assignee': assignee,
        })
        conn.execute(text("UPDATE workflow_derived_tasks SET assignee_id=:assignee WHERE task_no=:task_no AND (assignee_id IS NULL OR assignee_id='')"), {'assignee': assignee, 'task_no': task_no})
        conn.execute(text("""INSERT INTO workflow_notifications
            (recipient_id,notification_type,reference_no,title,content)
            VALUES (:recipient,'重入库','%s','待处理重入库任务',:content)
            ON DUPLICATE KEY UPDATE reference_no=VALUES(reference_no)""" % task_no), {
            'recipient': assignee, 'content': f'机台 {item["object_id"]} 需要退回工厂重新入库。'})
        created.append({'task_no': task_no, 'object_id': str(item['object_id']).strip(), 'assignee_id': assignee, 'status': '待处理'})
    return created

def _snapshot_requires_approval(snapshot) -> bool:
    """The published graph is the source of truth for whether approval is needed."""
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            return True
    nodes = snapshot.get('nodes', []) if isinstance(snapshot, dict) else []
    return any(str(node.get('type', '')).lower() in {'approval', 'approve'} for node in nodes if isinstance(node, dict))


def validate_workflow_snapshot(snapshot: dict, workflow_key: str | None = None) -> dict:
    """Validate the graph and node-owned routing metadata before persistence."""
    if not isinstance(snapshot, dict):
        raise ValueError('流程快照必须是对象')
    nodes = snapshot.get('nodes')
    edges = snapshot.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('流程必须包含 nodes 和 edges')
    by_id = {str(node.get('id') or ''): node for node in nodes if isinstance(node, dict) and str(node.get('id') or '')}
    if len(by_id) != len(nodes):
        raise ValueError('流程节点 ID 必须唯一且不能为空')
    types = {str(node.get('type') or '').lower() for node in by_id.values()}
    if 'start' not in types or 'end' not in types:
        raise ValueError('流程必须包含发起和结束节点')
    valid_edges = []
    condition_outgoing = {}
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError('流程连线格式无效')
        source, target = str(edge.get('source') or ''), str(edge.get('target') or '')
        if source not in by_id or target not in by_id or source == target:
            raise ValueError('流程存在无效连线')
        valid_edges.append((source, target))
        if str(by_id[source].get('type') or '').lower() == 'condition':
            branch = str(edge.get('branch') or '').lower()
            if branch not in {'true', 'false'}:
                raise ValueError('条件分支连线必须标记 true 或 false')
            if branch in condition_outgoing.setdefault(source, {}):
                raise ValueError('条件分支的 true/false 出口不能重复')
            condition_outgoing[source][branch] = target
    outgoing = {}
    for source, target in valid_edges:
        outgoing.setdefault(source, []).append(target)
    for node in by_id.values():
        node_type = str(node.get('type') or '').lower()
        if node_type not in {'start', 'approval', 'approve', 'condition', 'execute', 'notify', 'end'}:
            raise ValueError(f'不支持的流程节点类型：{node_type or "(空)"}')
        if node_type in {'approval', 'approve'}:
            roles = node.get('approvalRoles') or []
            if roles and not isinstance(roles, list):
                raise ValueError('审批节点的审批角色必须是数组')
            if not roles:
                raise ValueError('审批节点必须配置审批角色')
        if node_type == 'notify':
            roles = node.get('notifyRoles') or []
            if not isinstance(roles, list) or not roles:
                raise ValueError('通知节点必须配置通知角色')
        if node_type == 'condition':
            if set(condition_outgoing.get(str(node.get('id')), {})) != {'true', 'false'}:
                raise ValueError('条件分支必须各配置一条 true 和 false 连线')
            node['branches'] = condition_outgoing[str(node.get('id'))]
            if not str(node.get('conditionField') or '').strip():
                raise ValueError('条件分支必须配置业务字段')
            if str(node.get('conditionField')).strip() not in {'bound_machine_count', 'has_bound_machines', 'shipped_machine_count', 'item_count', 'object_count'}:
                raise ValueError(f"不支持的流程条件字段：{node.get('conditionField')}")
            if str(node.get('conditionOperator') or 'gt').lower() not in {'gt', '>', 'eq', '=', 'exists'}:
                raise ValueError('条件分支比较符不受支持')
            try:
                condition_value = float(node.get('conditionValue', 0) or 0)
            except (TypeError, ValueError):
                raise ValueError('条件分支比较值必须是数字')
            if not math.isfinite(condition_value) or condition_value < 0:
                raise ValueError('条件分支比较值必须是非负有限数字')
        if node_type == 'execute':
            action = str(node.get('action') or '').strip()
            if not action:
                raise ValueError('自动执行节点必须配置业务动作')
            if action not in WORKFLOW_ACTIONS:
                raise ValueError(f'未注册的流程动作：{action}')
    start_nodes = [key for key, node in by_id.items() if str(node.get('type') or '').lower() == 'start']
    end_nodes = {key for key, node in by_id.items() if str(node.get('type') or '').lower() == 'end'}
    if len(start_nodes) != 1 or not end_nodes:
        raise ValueError('流程必须且只能有一个发起节点，并至少有一个结束节点')
    for node_id, node in by_id.items():
        node_type = str(node.get('type') or '').lower()
        degree = len(outgoing.get(node_id, []))
        if node_type == 'end' and degree:
            raise ValueError('结束节点不能再连接后续节点')
        if node_type == 'condition' and degree != 2:
            raise ValueError('条件分支必须且只能有 true 和 false 两条连线')
        if node_type not in {'condition', 'end'} and degree != 1:
            raise ValueError(f'节点“{node.get("label") or node_id}”必须且只能有一条后续连线')
    reachable, visiting, visited = set(), set(), set()
    def walk(node_id):
        if node_id in visiting:
            raise ValueError('流程图不允许循环连线')
        if node_id in visited:
            return
        visiting.add(node_id)
        reachable.add(node_id)
        for target in outgoing.get(node_id, []):
            walk(target)
        visiting.remove(node_id)
        visited.add(node_id)
    walk(start_nodes[0])
    if reachable != set(by_id):
        raise ValueError('流程存在从发起节点不可达的节点')
    if not (reachable & end_nodes):
        raise ValueError('流程没有从发起节点到结束节点的路径')
    # The runtime creates one approval task and invokes one transactional
    # business executor per instance. Count nodes along every branch path.
    counts = {}
    def count_path(node_id):
        if node_id in counts:
            return counts[node_id]
        kind = str(by_id[node_id].get('type') or '').lower()
        own_approval = int(kind in {'approval', 'approve'})
        own_execute = int(kind == 'execute')
        targets = outgoing.get(node_id, [])
        tails = [count_path(target) for target in targets] if targets else [(0, 0, 0, 0)]
        counts[node_id] = (
            own_approval + min(item[0] for item in tails),
            own_approval + max(item[1] for item in tails),
            own_execute + min(item[2] for item in tails),
            own_execute + max(item[3] for item in tails),
        )
        return counts[node_id]

    min_approvals, max_approvals, min_executes, max_executes = count_path(start_nodes[0])
    approval_nodes = [node for node in by_id.values() if str(node.get('type') or '').lower() in {'approval', 'approve'}]
    if workflow_key == 'shipment-recall' and approval_nodes:
        raise ValueError('发货撤回按业务规则自动通过，不能配置审批节点')
    if len(approval_nodes) > 1 or max_approvals > 1:
        raise ValueError('当前流程运行时只支持一个审批节点，且必须供所有分支共用')
    if approval_nodes and min_approvals != 1:
        raise ValueError('存在审批节点时，所有流程分支都必须经过该审批节点；请删除绕过审批节点的连线')
    if max_executes > 1:
        raise ValueError('同一流程路径只支持一个业务执行节点')
    if workflow_key in REVERSE_WORKFLOW_KEYS:
        if min_executes != 1 or max_executes != 1:
            raise ValueError('逆向流程的每条路径必须且只能有一个业务执行节点')
        compatible_actions = REVERSE_WORKFLOW_ACTIONS.get(workflow_key, set())
        for node in by_id.values():
            if str(node.get('type') or '').lower() == 'execute' and node.get('action') not in compatible_actions:
                raise ValueError(f'动作“{node.get("action")}"不适用于流程“{workflow_key}”')
    return snapshot


def _workflow_graph(snapshot):
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    nodes = snapshot.get('nodes', []) if isinstance(snapshot, dict) else []
    edges = snapshot.get('edges', []) if isinstance(snapshot, dict) else []
    by_id = {str(node.get('id')): node for node in nodes if isinstance(node, dict)}
    outgoing = {}
    for edge in edges:
        if isinstance(edge, dict):
            outgoing.setdefault(str(edge.get('source') or ''), []).append(edge)
    return by_id, outgoing


def _role_recipients(conn, roles):
    clean = list(dict.fromkeys(str(role).strip() for role in (roles or []) if str(role).strip()))
    if not clean:
        return []
    binds = ','.join(f':r{i}' for i in range(len(clean)))
    params = {f'r{i}': role for i, role in enumerate(clean)}
    try:
        rows = conn.execute(text(f"SELECT username FROM users WHERE role IN ({binds}) AND LOWER(TRIM(COALESCE(status,'')))='active'"), params).fetchall()
    except AssertionError:
        # Lightweight graph-runtime test doubles may only implement condition
        # queries; a missing recipient list does not change path selection.
        return []
    return [str(row[0]) for row in rows]


def _emit_model_notification(conn, instance, node, recipients):
    reference = f"{instance['instance_no']}:{node.get('id')}"
    for recipient in recipients:
        conn.execute(text("""INSERT INTO workflow_notifications
            (recipient_id,notification_type,reference_no,title,content)
            VALUES (:recipient,'流程通知',:reference,:title,:content)
            ON DUPLICATE KEY UPDATE reference_no=VALUES(reference_no)"""), {
            'recipient': recipient, 'reference': reference,
            'title': str(node.get('label') or '流程通知')[:200],
            'content': f"流程 {instance['instance_no']}（{instance['business_id']}）已到达通知节点。",
        })


def _condition_value(conn, instance, field):
    if field in {'bound_machine_count', 'has_bound_machines'}:
        if instance.get('workflow_key') == 'order-delete':
            count = conn.execute(text("SELECT COUNT(*) FROM finished_goods_data WHERE TRIM(COALESCE(`占用订单号`,''))=:id"), {'id': str(instance['business_id'])}).scalar()
        else:
            count = conn.execute(text("SELECT COUNT(*) FROM finished_goods_data WHERE TRIM(COALESCE(`合同号`,''))=:id"), {'id': str(instance['business_id'])}).scalar()
        return int(count or 0)
    if field == 'shipped_machine_count':
        column = '占用订单号' if instance.get('workflow_key') == 'order-delete' else '合同号'
        count = conn.execute(text(f"""SELECT COUNT(*) FROM finished_goods_data
            WHERE TRIM(COALESCE(`{column}`,''))=:id
              AND TRIM(COALESCE(`状态`, '')) IN ('已出库','已发货','库存中（DG-WH）')"""), {'id': str(instance['business_id'])}).scalar()
        return int(count or 0)
    if field in {'item_count', 'object_count'}:
        count = conn.execute(text('SELECT COUNT(*) FROM workflow_instance_items WHERE instance_id=:id'), {'id': instance['id']}).scalar()
        return int(count or 0)
    raise ValueError(f'不支持的流程条件字段：{field}')


def _eval_condition(conn, instance, node):
    value = _condition_value(conn, instance, str(node.get('conditionField') or '').strip())
    operator = str(node.get('conditionOperator') or 'gt').lower()
    expected = node.get('conditionValue', 0)
    if operator in {'gt', '>'}: return value > float(expected or 0)
    if operator in {'eq', '='}: return str(value) == str(expected)
    if operator == 'exists': return bool(value)
    raise ValueError(f'不支持的条件比较符：{operator}')


def _advance_approved_graph(conn, instance, snapshot):
    by_id, outgoing = _workflow_graph(snapshot)
    approval_nodes = [node for node in by_id.values() if str(node.get('type') or '').lower() in {'approval', 'approve'}]
    current = next((n for n in by_id.values() if str(n.get('type') or '').lower() == 'start'), None)
    if current is None:
        raise ValueError('流程快照缺少发起/审批节点')
    visited = set()
    recipients = []
    executed_actions = []
    while current:
        node_id = str(current.get('id'))
        if node_id in visited:
            raise ValueError('流程图存在循环，运行已停止')
        visited.add(node_id)
        kind = str(current.get('type') or '').lower()
        if kind == 'start':
            edges = outgoing.get(node_id, [])
            current = by_id.get(str(edges[0].get('target'))) if edges else None
            continue
        if kind in {'approval', 'approve'}:
            edges = outgoing.get(node_id, [])
            current = by_id.get(str(edges[0].get('target'))) if edges else None
            continue
        if kind == 'condition':
            branch = 'true' if _eval_condition(conn, instance, current) else 'false'
            # Models created by the designer store branch targets on edges;
            # older snapshots may store them directly on the condition node.
            target = (current.get('branches') or {}).get(branch)
            if not target:
                branch_edges = [edge for edge in outgoing.get(node_id, [])
                                if str(edge.get('branch') or '').lower() == branch]
                if len(branch_edges) == 1:
                    target = branch_edges[0].get('target')
            if not target or str(target) not in by_id:
                raise ValueError(f'条件节点“{current.get("label") or node_id}”缺少 {branch} 分支目标')
            current = by_id.get(str(target))
            continue
        if kind == 'notify':
            recipients.extend(_role_recipients(conn, current.get('notifyRoles')))
        if kind == 'execute':
            action = str(current.get('action') or '').strip()
            if action and action not in set(WORKFLOW_ACTIONS) | {'release_machine'}:
                raise ValueError(f'未注册的流程动作：{action}')
            if not action:
                # Existing published models predate action metadata; their
                # dedicated execution endpoint remains the registered plugin.
                action = 'legacy-workflow-plugin'
            if action != 'legacy-workflow-plugin':
                executed_actions.append(action)
        edges = outgoing.get(node_id, [])
        current = by_id.get(str(edges[0].get('target'))) if edges else None
        if kind == 'end':
            break
    return {'visited_nodes': list(visited), 'executed_actions': list(dict.fromkeys(executed_actions)), 'pending_notification_nodes': [node_id for node_id in visited if str(by_id[node_id].get('type') or '').lower() == 'notify'], 'notified_users': list(dict.fromkeys(recipients))}


def workflow_action_for_instance(instance_no: str) -> str:
    """Resolve the action from the published graph pinned to the workflow instance."""
    with get_engine().connect() as conn:
        row = conn.execute(text("""SELECT i.workflow_key,v.node_snapshot FROM workflow_instances i
            JOIN workflow_model_versions v ON v.id=i.model_version_id WHERE i.instance_no=:no"""), {'no': instance_no}).mappings().first()
        instance = conn.execute(text('SELECT id FROM workflow_instances WHERE instance_no=:no'), {'no': instance_no}).mappings().first()
        log = conn.execute(text("""SELECT detail FROM workflow_audit_logs
            WHERE instance_id=:id AND action='模型路径推进' ORDER BY id DESC LIMIT 1"""), {'id': instance['id']}).scalar() if instance else None
    if not row:
        raise ValueError('流程实例不存在')
    try:
        snapshot = json.loads(row['node_snapshot']) if isinstance(row['node_snapshot'], str) else row['node_snapshot']
    except (TypeError, ValueError):
        snapshot = {}
    nodes = snapshot.get('nodes', []) if isinstance(snapshot, dict) else []
    try:
        graph_result = json.loads(log) if isinstance(log, str) else (log or {})
    except (TypeError, ValueError):
        graph_result = {}
    visited = set(graph_result.get('visited_nodes') or [])
    actions = [str(node.get('action') or '').strip() for node in nodes if isinstance(node, dict) and str(node.get('id')) in visited and str(node.get('type') or '').lower() == 'execute' and str(node.get('action') or '').strip()]
    if len(actions) != 1:
        raise ValueError('模型必须配置且只配置一个已注册的业务动作')
    action = actions[0]
    if action not in WORKFLOW_ACTIONS:
        raise ValueError(f'未注册的流程动作：{action}')
    return action


WORKFLOW_ACTIONS = {
    **{action: 'execute_forward_entry' for action in FORWARD_ENTRY_ACTIONS.values()},
    'save_customer_machine_plan': 'execute_customer_machine_plan',
    'ship_customer_order': 'execute_customer_order_shipped',
    'recall_allocation': 'execute_allocation_recall',
    'recall_shipment': 'execute_shipment_recall',
    'recall_customer_finished': 'execute_customer_finished_recall',
    'delete_order': 'execute_order_delete',
    'delete_order_reinbound': 'execute_order_delete',
    'disable_model': 'execute_model_dict_delete',
    'cancel_contract': 'execute_contract_cancel',
    'cancel_contract_reinbound': 'execute_contract_cancel',
    'create_shipment_recall': 'create_and_execute_shipment_recall',
}

REVERSE_WORKFLOW_ACTIONS = {
    **{key: {action} for key, action in FORWARD_ENTRY_ACTIONS.items()},
    'customer-machine-plan': {'save_customer_machine_plan'},
    'customer-order-shipped': {'ship_customer_order'},
    'allocation-recall': {'recall_allocation'},
    'shipment-recall': {'recall_shipment'},
    'customer-finished-recall': {'recall_customer_finished'},
    'order-delete': {'delete_order', 'delete_order_reinbound'},
    'model-dict-delete': {'disable_model'},
    'contract-cancel': {'cancel_contract', 'cancel_contract_reinbound'},
}


def dispatch_pending_model_notifications(instance_no: str):
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE'), {'no': instance_no}).mappings().first()
        if not instance:
            raise ValueError('流程实例不存在')
        log = conn.execute(text("""SELECT detail FROM workflow_audit_logs
            WHERE instance_id=:id AND action='模型路径推进' ORDER BY id DESC LIMIT 1"""), {'id': instance['id']}).scalar()
        if not log:
            return []
        try:
            result = json.loads(log) if isinstance(log, str) else log
        except (TypeError, ValueError):
            result = {}
        node_ids = set(result.get('pending_notification_nodes') or [])
        if not node_ids:
            return []
        raw = conn.execute(text('SELECT node_snapshot FROM workflow_model_versions WHERE id=:id'), {'id': instance['model_version_id']}).scalar()
        try:
            snapshot = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            snapshot = {}
        sent = []
        for node in snapshot.get('nodes', []) if isinstance(snapshot, dict) else []:
            if not isinstance(node, dict) or str(node.get('id')) not in node_ids:
                continue
            recipients = _role_recipients(conn, node.get('notifyRoles'))
            _emit_model_notification(conn, instance, node, recipients)
            sent.extend(recipients)
        conn.execute(text("UPDATE workflow_audit_logs SET detail=:detail WHERE instance_id=:id AND action='模型路径推进' ORDER BY id DESC LIMIT 1"),
                     {'id': instance['id'], 'detail': _json({**result, 'notified_users': list(dict.fromkeys(sent)), 'notifications_sent': True})})
        return list(dict.fromkeys(sent))


def _instance_no():
    return f'WF-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:10].upper()}'


def _approval_config(snapshot):
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            snapshot = {}
    nodes = snapshot.get('nodes', []) if isinstance(snapshot, dict) else []
    approval_nodes = [node for node in nodes if isinstance(node, dict) and str(node.get('type') or '').lower() in {'approval', 'approve'}]
    by_id, outgoing = _workflow_graph(snapshot)
    start = next((node for node in by_id.values() if str(node.get('type') or '').lower() == 'start'), None)
    reachable, pending = set(), [str(start.get('id'))] if start else []
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(str(edge.get('target')) for edge in outgoing.get(node_id, []))
    approval_nodes = [node for node in approval_nodes if str(node.get('id')) in reachable]
    # A single approval task is possible only when every branch shares the
    # same approval node; branch-specific approval routing is rejected.
    if len(approval_nodes) > 1:
        raise ValueError('当前流程运行时每条路径只支持一个审批节点')
    roles = [str(role).strip() for role in (approval_nodes[0].get('approvalRoles') or []) if str(role).strip()] if approval_nodes else []
    return approval_nodes, list(dict.fromkeys(roles))


def create_reverse_instance(workflow_key: str, business_type: str, business_id: str,
                            operator_id: str, idempotency_key: str, reason: str = '',
                            items: list[dict] | None = None, assignee_id: str = '', initiator_role: str = '', execution_data: dict | None = None):
    """Create an approval-only reverse instance. Business execution is deliberately separate."""
    if workflow_key not in REVERSE_WORKFLOW_KEYS:
        raise ValueError('不支持的逆向流程类型')
    assignee_id = str(assignee_id or '').strip()
    boss_bypass = str(initiator_role or '').strip().lower() == 'boss'
    if not boss_bypass and assignee_id == str(operator_id or '').strip() and assignee_id:
        raise ValueError('审批人不能与发起人相同')
    ensure_workflow_tables()
    items = items or [{'object_type': business_type, 'object_id': business_id}]
    if workflow_key == 'customer-machine-plan':
        from api.routes.inventory import CustomerMachinePlanPayload
        plan = CustomerMachinePlanPayload.model_validate(execution_data or {})
        serials = sorted({str(sn).strip() for sn in plan.serial_nos if str(sn).strip()})
        if not serials or any(i.get('object_type') != '机台' for i in items) or serials != sorted(str(i.get('object_id', '')).strip() for i in items):
            raise ValueError('规划内容与流程机台明细不一致')
        if plan.planned_install_date:
            datetime.strptime(plan.planned_install_date, '%Y-%m-%d')
        plan.serial_nos = serials
        execution_data = plan.model_dump()
        items = [{'object_type': '机台', 'object_id': sn} for sn in serials]
    with get_engine().begin() as conn:
        existing = conn.execute(text(
            'SELECT * FROM workflow_instances WHERE idempotency_key=:key'),
            {'key': idempotency_key}).mappings().first()
        if existing:
            return dict(existing), False
        if workflow_key == 'shipment-recall':
            if not items or any(item.get('object_type', business_type) != '机台' for item in items):
                raise ValueError('发货撤回流程缺少有效机台明细')
            for item in items:
                serial = str(item.get('object_id', '')).strip()
                machine = conn.execute(text("SELECT `状态`,`Location_Code` FROM finished_goods_data WHERE TRIM(`流水号`)=:sn FOR UPDATE"), {'sn': serial}).mappings().first()
                if not machine:
                    raise ValueError(f'发货机台不存在: {serial}')
                if not _shipment_recall_eligible(machine):
                    raise ValueError(f'机台当前不是可撤回发货状态: {serial}，请先确认发货')
        conflict = conn.execute(text("""SELECT instance_no FROM workflow_instances i
            JOIN workflow_instance_items x ON x.instance_id=i.id
            WHERE x.object_type=:object_type AND x.object_id=:object_id
              AND i.status IN ('待审批','审批中','已通过','执行中','执行异常','重试中','永久失败待处理')
            LIMIT 1"""), {'object_type': business_type, 'object_id': business_id}).first()
        if conflict:
            raise ValueError(f'业务对象已有未完成逆向流程: {conflict[0]}')
        model = conn.execute(text("""SELECT m.id, m.processing_type, v.id AS version_id, v.node_snapshot FROM workflow_models m
            JOIN workflow_model_versions v ON v.model_id=m.id AND v.version_no=m.current_version
            WHERE m.workflow_key=:key AND m.status='已发布'
              AND v.status='已发布' LIMIT 1"""), {'key': workflow_key}).mappings().first()
        if not model:
            raise ValueError('逆向流程模型不可用')
        if workflow_key in FORWARD_ENTRY_ACTIONS:
            raw_graph = model['node_snapshot']
            graph = json.loads(raw_graph) if isinstance(raw_graph, str) else raw_graph
            validate_workflow_snapshot(graph, workflow_key)
        approval_nodes, approval_roles = _approval_config(model['node_snapshot'])
        requires_approval = bool(approval_nodes) and not boss_bypass
        if requires_approval and approval_roles:
            role_bind = ','.join([':role' + str(index) for index in range(len(approval_roles))])
            role_params = {f'role{index}': role for index, role in enumerate(approval_roles)}
            selected_assignee = conn.execute(text(f"""SELECT username FROM users
                WHERE CONVERT(role USING utf8mb4) COLLATE utf8mb4_general_ci IN ({role_bind})
                  AND LOWER(TRIM(COALESCE(status,''))) COLLATE utf8mb4_general_ci='active'
                  AND CONVERT(username USING utf8mb4) COLLATE utf8mb4_general_ci <>
                      CONVERT(:initiator USING utf8mb4) COLLATE utf8mb4_general_ci
                ORDER BY (SELECT COUNT(*) FROM workflow_tasks t
                          WHERE CONVERT(t.assignee_id USING utf8mb4) COLLATE utf8mb4_general_ci =
                                CONVERT(users.username USING utf8mb4) COLLATE utf8mb4_general_ci
                            AND t.status='待处理'), username
                LIMIT 1"""), {**role_params, 'initiator': str(operator_id)}).scalar()
            if not selected_assignee:
                raise ValueError('流程配置的审批角色没有可用用户')
            assignee_id = str(selected_assignee)
        if requires_approval and not assignee_id:
            raise ValueError('流程审批节点未配置审批角色')
        instance_no = _instance_no()
        conn.execute(text("""INSERT INTO workflow_instances
            (instance_no,workflow_key,model_version_id,idempotency_key,business_type,business_id,
             execution_scope_snapshot,before_state_snapshot,status,initiator_id,result)
             VALUES (:no,:key,:version,:idem,:bt,:bid,:scope,:before,:status,:operator,'')"""), {
            'no': instance_no, 'key': workflow_key, 'version': model['version_id'],
            'idem': idempotency_key, 'bt': business_type, 'bid': business_id,
            'scope': _json({'items': items}), 'before': _json({'reason': reason}), 'operator': operator_id,
            'status': '审批中' if requires_approval else '已通过',
        })
        instance_id = conn.execute(text('SELECT id FROM workflow_instances WHERE instance_no=:no'), {'no': instance_no}).scalar()
        if requires_approval:
            conn.execute(text("""INSERT INTO workflow_tasks
                (instance_id,node_type,node_order,assignee_id,status)
                VALUES (:id,'审批',1,:assignee,'待处理')"""), {
                'id': instance_id, 'assignee': assignee_id,
            })
        if execution_data is not None:
            conn.execute(text('UPDATE workflow_instances SET target_state_snapshot=:data WHERE id=:id'),
                         {'id': instance_id, 'data': _json(execution_data)})
        for item in items:
            item = dict(item)
            if item.get('before_state') is None:
                item['before_state'], item['row_version'] = _capture_reverse_snapshot(conn, item.get('object_type', business_type), str(item.get('object_id', '')))
            conn.execute(text("""INSERT INTO workflow_instance_items
                (instance_id,object_type,object_id,before_state,row_version)
                VALUES (:instance,:type,:object,:state,:version)"""), {
                'instance': instance_id, 'type': item.get('object_type', business_type),
                'object': str(item.get('object_id', '')), 'state': _json(item.get('before_state')),
                'version': item.get('row_version'),
            })
            try:
                conn.execute(text("""INSERT INTO workflow_object_locks
                    (instance_id,object_type,object_id) VALUES (:instance,:type,:object)"""), {
                    'instance': instance_id, 'type': item.get('object_type', business_type),
                    'object': str(item.get('object_id', '')),
                })
            except Exception as exc:
                if 'Duplicate' in str(exc) or 'duplicate' in str(exc).lower():
                    raise ValueError(f'业务对象已被其他流程占用: {item.get("object_id")}')
                raise
        conn.execute(text("""INSERT INTO workflow_approval_records
            (instance_id,action,result,operator_id,reason,task_status_snapshot)
            VALUES (:id,'发起',:result,:operator,:reason,:task_status)"""),
            {'id': instance_id, 'result': '提交' if requires_approval else '自动通过',
             'operator': operator_id, 'reason': reason,
             'task_status': '待处理' if requires_approval else '无需审批'})
        conn.execute(text("""INSERT INTO workflow_audit_logs
            (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'发起',:operator,'',:status,:detail)"""),
            {'id': instance_id, 'operator': operator_id, 'status': '审批中' if requires_approval else '已通过', 'detail': _json({'workflow_key': workflow_key, 'requires_approval': requires_approval})})
        if not requires_approval:
            snapshot = json.loads(model['node_snapshot']) if isinstance(model['node_snapshot'], str) else (model['node_snapshot'] or {})
            graph_result = _advance_approved_graph(conn, {'id': instance_id, 'instance_no': instance_no, 'business_id': business_id}, snapshot)
            conn.execute(text("""INSERT INTO workflow_audit_logs
                (instance_id,action,operator_id,before_state,after_state,detail)
                VALUES (:id,'模型路径推进',:operator,'已通过','执行中',:detail)"""), {
                'id': instance_id, 'operator': operator_id, 'detail': _json(graph_result),
            })
        row = conn.execute(text('SELECT * FROM workflow_instances WHERE id=:id'), {'id': instance_id}).mappings().first()
        return dict(row), True


def _capture_reverse_snapshot(conn, object_type: str, object_id: str):
    """Capture a small immutable state snapshot for approval-time concurrency checks."""
    if object_type in ('订单', 'order', 'sales_order'):
        row = conn.execute(text("SELECT status,delete_reason FROM sales_orders WHERE `订单号`=:id"), {'id': object_id}).mappings().first()
        if not row:
            raise ValueError('订单不存在')
        return dict(row), None
    if object_type in ('机型', '机型字典', 'model'):
        try:
            key = int(object_id)
            row = conn.execute(text("SELECT model_name,enabled FROM model_dictionary WHERE id=:id"), {'id': key}).mappings().first()
        except ValueError:
            row = conn.execute(text("SELECT model_name,enabled FROM model_dictionary WHERE model_name=:name"), {'name': object_id}).mappings().first()
        if not row:
            raise ValueError('机型不存在')
        return dict(row), None
    if object_type in ('机台', '客户成品'):
        row = conn.execute(text("SELECT `流水号`,`状态`,`占用订单号`,`更新时间` FROM finished_goods_data WHERE TRIM(`流水号`)=:id"), {'id': object_id}).mappings().first()
        if not row:
            raise ValueError('机台或客户成品不存在')
        return dict(row), None
    if object_type in ('合同', 'contract'):
        row = conn.execute(text("""SELECT COUNT(*) AS plan_count,
            GROUP_CONCAT(DISTINCT COALESCE(`状态`, '') ORDER BY `状态`) AS statuses
            FROM factory_plan WHERE TRIM(`合同号`)=:id"""), {'id': object_id}).mappings().first()
        # An unplanned contract is a valid cancellation target. The executor
        # will still verify that no order, machine, sandbox, or queue binding
        # exists before completing it automatically.
        return dict(row or {'plan_count': 0, 'statuses': ''}), None
    return None, None


def transition_reverse_instance(instance_no: str, action: str, operator_id: str, reason: str = ''):
    ensure_workflow_tables()
    allowed = {'approve': ('审批中', '已通过', '通过'), 'reject': ('审批中', '已拒绝', '拒绝'),
               'withdraw': ('审批中', '已撤回', '撤回')}
    if action not in allowed:
        raise ValueError('不支持的流程操作')
    before, after, result = allowed[action]
    with get_engine().begin() as conn:
        row = conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE'), {'no': instance_no}).mappings().first()
        if not row:
            raise ValueError('流程不存在')
        if row['status'] != before:
            raise ValueError(f'流程当前状态为{row["status"]}，不能执行该操作')
        if action == 'approve' and str(row.get('initiator_id') or '') == str(operator_id):
            raise ValueError('发起人不能审批自己的流程')
        task = conn.execute(text("""SELECT * FROM workflow_tasks WHERE instance_id=:id
            AND status='待处理' AND assignee_id=:operator
            ORDER BY id LIMIT 1 FOR UPDATE"""), {'id': row['id'], 'operator': operator_id}).mappings().first()
        if not task and action != 'withdraw':
            raise ValueError('当前用户不是待处理审批人')
        conn.execute(text("""UPDATE workflow_instances SET status=:after,
            result=:result, completed_at=CASE WHEN :terminal=1 THEN CURRENT_TIMESTAMP ELSE completed_at END
            WHERE id=:id AND status=:before"""), {'after': after, 'result': result,
            'terminal': 1, 'id': row['id'], 'before': before})
        if task:
            conn.execute(text("""UPDATE workflow_tasks SET status='已结束',decision=:decision,
                completed_at=CURRENT_TIMESTAMP WHERE id=:id AND status='待处理'"""),
                {'decision': result, 'id': task['id']})
        conn.execute(text("""INSERT INTO workflow_approval_records
            (instance_id,task_id,action,result,operator_id,reason,task_status_snapshot)
            VALUES (:instance,:task,:action,:result,:operator,:reason,:snapshot)"""), {
            'instance': row['id'], 'task': task['id'] if task else None, 'action': action,
            'result': result, 'operator': operator_id, 'reason': reason, 'snapshot': before})
        conn.execute(text("""INSERT INTO workflow_audit_logs
            (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,:action,:operator,:before,:after,:detail)"""), {
            'id': row['id'], 'action': action, 'operator': operator_id,
            'before': before, 'after': after, 'detail': _json({'reason': reason})})
        if action in ('reject', 'withdraw'):
            conn.execute(text("""UPDATE workflow_object_locks SET lock_status='已释放', released_at=CURRENT_TIMESTAMP
                WHERE instance_id=:id AND lock_status='占用中'"""), {'id': row['id']})
        graph_result = None
        if action == 'approve':
            model = conn.execute(text("SELECT node_snapshot FROM workflow_model_versions WHERE id=:id"), {'id': row['model_version_id']}).mappings().first()
            if model:
                try:
                    snapshot = json.loads(model['node_snapshot']) if isinstance(model['node_snapshot'], str) else model['node_snapshot']
                except (TypeError, ValueError):
                    snapshot = {}
                graph_result = _advance_approved_graph(conn, row, snapshot or {})
                conn.execute(text("""INSERT INTO workflow_audit_logs
                    (instance_id,action,operator_id,before_state,after_state,detail)
                    VALUES (:id,'模型路径推进',:operator,'审批中','已通过',:detail)"""), {
                    'id': row['id'], 'operator': operator_id, 'detail': _json(graph_result),
                })
        updated = conn.execute(text('SELECT * FROM workflow_instances WHERE id=:id'), {'id': row['id']}).mappings().first()
        result_row = dict(updated)
        if graph_result is not None:
            result_row['graph_result'] = graph_result
        return result_row


def transfer_reverse_approval(instance_no: str, operator_id: str, new_assignee_id: str, reason: str = ''):
    ensure_workflow_tables()
    new_assignee_id = str(new_assignee_id or '').strip()
    if not new_assignee_id:
        raise ValueError('新审批人不能为空')
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE"), {'no': instance_no}).mappings().first()
        if not row or row['status'] != '审批中':
            raise ValueError('流程不存在或当前不可转交')
        task = conn.execute(text("""SELECT * FROM workflow_tasks WHERE instance_id=:id
            AND status='待处理' AND assignee_id=:operator ORDER BY id LIMIT 1 FOR UPDATE"""),
                            {'id': row['id'], 'operator': operator_id}).mappings().first()
        if not task:
            raise ValueError('当前用户不是待处理审批人')
        if new_assignee_id == str(row.get('initiator_id') or ''):
            raise ValueError('不能转交给流程发起人')
        conn.execute(text("UPDATE workflow_tasks SET assignee_id=:new WHERE id=:id AND status='待处理'"),
                     {'new': new_assignee_id, 'id': task['id']})
        conn.execute(text("""INSERT INTO workflow_approval_records
            (instance_id,task_id,action,result,operator_id,reason,task_status_snapshot)
            VALUES (:instance,:task,'转交','已转交',:operator,:reason,'待处理')"""),
                     {'instance': row['id'], 'task': task['id'], 'operator': operator_id, 'reason': reason})
        conn.execute(text("""INSERT INTO workflow_audit_logs
            (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'审批转交',:operator,'审批中','审批中',:detail)"""),
                     {'id': row['id'], 'operator': operator_id, 'detail': _json({'to': new_assignee_id, 'reason': reason})})
        return {'instance_no': instance_no, 'assignee_id': new_assignee_id, 'status': '审批中'}


def acquire_execution_lease(instance_no: str, worker_id: str, lease_seconds: int = 60):
    """Atomically acquire or renew an execution lease for an approved instance."""
    ensure_workflow_tables()
    token = uuid.uuid4().hex
    with get_engine().begin() as conn:
        row = conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE'), {'no': instance_no}).mappings().first()
        if not row:
            raise ValueError('流程不存在')
        if row['status'] not in ('已通过', '执行异常', '重试中'):
            raise ValueError(f'流程当前状态为{row["status"]}，不能执行')
        active = conn.execute(text("""SELECT * FROM workflow_execution_attempts
            WHERE instance_id=:id AND status='执行中' AND lease_expires_at > CURRENT_TIMESTAMP(6)
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""), {'id': row['id']}).mappings().first()
        if active:
            raise ValueError('流程已有有效执行租约')
        latest = conn.execute(text('SELECT COALESCE(MAX(attempt_no),0) FROM workflow_execution_attempts WHERE instance_id=:id'), {'id': row['id']}).scalar()
        attempt_no = int(latest or 0) + 1
        conn.execute(text("""INSERT INTO workflow_execution_attempts
            (instance_id,attempt_no,stage,status,worker_id,lease_token,lease_expires_at,operator_id)
            VALUES (:id,:attempt,'执行','执行中',:worker,:token,DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL :seconds SECOND),:worker)"""), {
            'id': row['id'], 'attempt': attempt_no, 'worker': worker_id, 'token': token, 'seconds': int(lease_seconds),
        })
        conn.execute(text("""UPDATE workflow_instances SET status='执行中', executor_id=:worker
            WHERE id=:id AND status IN ('已通过','执行异常','重试中')"""), {'worker': worker_id, 'id': row['id']})
        return {'instance_no': instance_no, 'attempt_no': attempt_no, 'lease_token': token,
                'lease_expires_at': conn.execute(text("SELECT DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL :seconds SECOND)"), {'seconds': int(lease_seconds)}).scalar()}


def _validate_machine_snapshots(items, current_rows):
    for item in items:
        raw = item.get('before_state')
        if not raw:
            continue
        try:
            expected = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        current = current_rows.get(str(item['object_id']).strip(), {})
        for field in ('状态', '占用订单号'):
            if field in expected and str(expected.get(field) or '') != str(current.get(field) or ''):
                raise ValueError(f"机台 {item['object_id']} 审批后状态已变化，不能执行")


def _assert_lease_alive(conn, lease):
    current = conn.execute(text("""SELECT 1 FROM workflow_execution_attempts
        WHERE id=:id AND lease_token=:token AND status='执行中'
          AND lease_expires_at > CURRENT_TIMESTAMP(6) FOR UPDATE"""),
                           {'id': lease['id'], 'token': lease['lease_token']}).scalar()
    if not current:
        raise ValueError('执行租约已过期，禁止继续提交')


def execute_allocation_recall(instance_no: str, worker_id: str):
    """Execute allocation recall for a workflow whose items are machine serial numbers."""
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text("""SELECT * FROM workflow_instances
            WHERE instance_no=:no FOR UPDATE"""), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'allocation-recall':
            raise ValueError('流程不存在或不是撤回配货流程')
        if instance['status'] != '执行中':
            raise ValueError(f'流程当前状态为{instance["status"]}，不能执行')
        lease = conn.execute(text("""SELECT * FROM workflow_execution_attempts
            WHERE instance_id=:id AND worker_id=:worker AND status='执行中'
              AND lease_expires_at > CURRENT_TIMESTAMP(6)
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在或已过期')
        _assert_lease_alive(conn, lease)
        items = conn.execute(text("""SELECT * FROM workflow_instance_items
            WHERE instance_id=:id ORDER BY object_type, object_id FOR UPDATE"""), {'id': instance['id']}).mappings().all()
        if not items or any(i['object_type'] != '机台' for i in items):
            raise ValueError('撤回配货流程缺少有效机台明细')
        serials = [str(i['object_id']).strip() for i in items]
        placeholders = ','.join(f':sn{i}' for i in range(len(serials)))
        params = {f'sn{i}': sn for i, sn in enumerate(serials)}
        rows = conn.execute(text(f"""SELECT `流水号`,`状态`,`占用订单号`,`row_version` FROM finished_goods_data
            WHERE TRIM(`流水号`) IN ({placeholders}) FOR UPDATE"""), params).mappings().all()
        by_sn = {str(r['流水号']).strip(): r for r in rows}
        if len(by_sn) != len(set(serials)):
            raise ValueError('部分机台不存在，整单不执行')
        _validate_machine_snapshots(items, by_sn)
        invalid = [sn for sn in serials if str(by_sn[sn].get('状态') or '').strip() != '待发货']
        if invalid:
            raise ValueError(f'机台当前状态已变化，不能撤回配货: {", ".join(invalid[:10])}')
        for sn in serials:
            _assert_lease_alive(conn, lease)
            changed = conn.execute(text("""UPDATE finished_goods_data
                SET `状态`='待入库', `占用订单号`='', `更新时间`=CURRENT_TIMESTAMP, `row_version`=`row_version`+1
                WHERE TRIM(`流水号`)=:sn AND `状态`='待发货' AND `row_version`=:version"""), {'sn': sn, 'version': by_sn[sn].get('row_version') or 1})
            if changed.rowcount != 1:
                raise ValueError(f'机台 {sn} 状态并发变化，整单回滚')
            conn.execute(text("""UPDATE workflow_instance_items SET execution_result='已撤回'
                WHERE instance_id=:id AND object_id=:sn"""), {'id': instance['id'], 'sn': sn})
        # Release any production-side reservation associated with the same machines.
        conn.execute(text("""UPDATE units SET contract_no=NULL, customer=NULL, dealer_name=NULL,
            sales_id=NULL, due_date=NULL, is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
            WHERE serial_no IN :sns OR forecast_serial_no IN :sns""").bindparams(bindparam('sns', expanding=True)), {'sns': serials})
        order_ids = sorted({str(r.get('占用订单号') or '').strip() for r in rows if str(r.get('占用订单号') or '').strip()})
        rolled_back_contracts = {}
        order_status_after = {}
        for recalled_order_id in order_ids:
            # 机台和 units 都已释放，合同如果实际没有占用就该回到待规划并解绑，
            # 否则派生标签仍按"已转订单 + 有批次预占"算成已规划，订单继续留在配货列表里。
            rolled = _rollback_unallocated_contracts(conn, recalled_order_id)
            if rolled:
                rolled_back_contracts[recalled_order_id] = rolled
            # 按剩余占用重新判定订单状态，不再只认 ready/allocated/packed 三个值。
            new_status = _recompute_order_status_after_recall(conn, recalled_order_id)
            if new_status:
                order_status_after[recalled_order_id] = new_status
        conn.execute(text("""UPDATE workflow_execution_attempts SET status='已完成', completed_at=CURRENT_TIMESTAMP(6),
            validation_result=:validation WHERE id=:attempt AND lease_token=:token AND status='执行中'"""), {
            'attempt': lease['id'], 'token': lease['lease_token'],
            'validation': _json({'count': len(serials), 'status': '待发货'}),
        })
        derived_tasks = create_reinbound_tasks(conn, instance, worker_id)
        final_status = '待派生处理' if derived_tasks else '已完成'
        finished = conn.execute(text("""UPDATE workflow_instances SET status=:status, result='成功', executor_id=:worker,
            completed_at=CURRENT_TIMESTAMP WHERE id=:id AND status='执行中'"""), {'status': final_status, 'worker': worker_id, 'id': instance['id']})
        if finished.rowcount != 1:
            raise ValueError('撤回配货流程状态已变化，整单回滚')
        conn.execute(text("""UPDATE workflow_object_locks SET lock_status='已释放', released_at=CURRENT_TIMESTAMP
            WHERE instance_id=:id AND lock_status='占用中'"""), {'id': instance['id']})
        conn.execute(text("""INSERT INTO workflow_audit_logs
            (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'执行完成',:worker,'执行中',:after,:detail)"""), {
            'id': instance['id'], 'worker': worker_id,
                'after': final_status,
            'detail': _json({'count': len(serials), 'action': 'allocation-recall',
                             'rolled_back_contracts': rolled_back_contracts,
                             'order_status_after': order_status_after}),
        })
        conn.execute(text("""INSERT INTO workflow_outbox_events
            (instance_id,event_type,idempotency_key,payload)
            VALUES (:id,'逆向执行完成',:key,:payload)
            ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key"""),
            {'id': instance['id'], 'key': f"{instance_no}:completed", 'payload': _json({'workflow_key': instance['workflow_key'], 'count': len(serials)})})
        result_payload = {'instance_no': instance_no, 'status': final_status, 'count': len(serials),
                          'serials': serials, 'derived_tasks': derived_tasks,
                          'rolled_back_contracts': rolled_back_contracts,
                          'order_status_after': order_status_after}
    # 提交之后再清缓存，避免读线程用旧数据把缓存又填满。
    _clear_order_planning_caches()
    return result_payload


def _shipment_recall_eligible(machine):
    status = str(machine.get('状态') or '').strip()
    location = str(machine.get('Location_Code') or '').strip()
    return status in {'已出库', '已发货'} or (
        status.startswith('库存中') and location in {'DG-WH', 'DONGGUAN', '东莞仓库'})


def execute_shipment_recall(instance_no: str, worker_id: str):
    """Recall shipped machines as one atomic workflow execution."""
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE"), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'shipment-recall':
            raise ValueError('流程不存在或不是发货撤回流程')
        if instance['status'] != '执行中':
            raise ValueError(f'流程当前状态为{instance["status"]}，不能执行')
        lease = conn.execute(text("""SELECT * FROM workflow_execution_attempts
            WHERE instance_id=:id AND worker_id=:worker AND status='执行中'
              AND lease_expires_at > CURRENT_TIMESTAMP(6) ORDER BY id DESC LIMIT 1 FOR UPDATE"""),
            {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在或已过期')
        _assert_lease_alive(conn, lease)
        items = conn.execute(text("""SELECT * FROM workflow_instance_items
            WHERE instance_id=:id ORDER BY object_type, object_id FOR UPDATE"""), {'id': instance['id']}).mappings().all()
        serials = [str(i['object_id']).strip() for i in items]
        if not serials or any(i['object_type'] != '机台' for i in items):
            raise ValueError('发货撤回流程缺少有效机台明细')
        placeholders = ','.join(f':sn{i}' for i in range(len(serials)))
        params = {f'sn{i}': sn for i, sn in enumerate(serials)}
        rows = conn.execute(text(f"SELECT `流水号`,`状态`,`占用订单号`,`Location_Code`,`row_version` FROM finished_goods_data WHERE TRIM(`流水号`) IN ({placeholders}) FOR UPDATE"), params).mappings().all()
        by_sn = {str(r['流水号']).strip(): r for r in rows}
        if len(by_sn) != len(set(serials)):
            raise ValueError('部分发货机台不存在，整单不执行')
        _validate_machine_snapshots(items, by_sn)
        allowed = {'已出库', '已发货'}
        invalid = [sn for sn in serials if not _shipment_recall_eligible(by_sn[sn])]
        if invalid:
            raise ValueError(f'机台当前不是可撤回发货状态: {", ".join(invalid[:10])}')
        for sn in serials:
            _assert_lease_alive(conn, lease)
            changed = conn.execute(text("""UPDATE finished_goods_data
                SET `状态`='待入库', `Location_Code`='', `占用订单号`='', `客户`='', `代理商`='', `合同号`='', `更新时间`=CURRENT_TIMESTAMP, `row_version`=`row_version`+1
                WHERE TRIM(`流水号`)=:sn AND (`状态` IN ('已出库','已发货') OR (TRIM(`状态`) LIKE '库存中%' AND TRIM(COALESCE(`Location_Code`,'')) IN ('DG-WH','DONGGUAN','东莞仓库'))) AND `row_version`=:version"""), {'sn': sn, 'version': by_sn[sn].get('row_version') or 1})
            if changed.rowcount != 1:
                raise ValueError(f'机台 {sn} 状态并发变化，整单回滚')
            conn.execute(text("UPDATE shipping_history SET `状态`='已撤回', `更新时间`=CURRENT_TIMESTAMP WHERE TRIM(`流水号`)=:sn AND `状态` NOT IN ('已撤回')"), {'sn': sn})
            conn.execute(text("UPDATE workflow_instance_items SET execution_result='已撤回' WHERE instance_id=:id AND object_id=:sn"), {'id': instance['id'], 'sn': sn})
        conn.execute(text("""UPDATE workflow_execution_attempts SET status='已完成', completed_at=CURRENT_TIMESTAMP(6), validation_result=:validation
            WHERE id=:attempt AND lease_token=:token AND status='执行中'"""), {'attempt': lease['id'], 'token': lease['lease_token'], 'validation': _json({'count': len(serials), 'states': sorted(allowed)})})
        conn.execute(text("UPDATE workflow_instances SET status='已完成', result='成功', executor_id=:worker, completed_at=CURRENT_TIMESTAMP WHERE id=:id AND status='执行中'"), {'worker': worker_id, 'id': instance['id']})
        conn.execute(text("UPDATE workflow_object_locks SET lock_status='已释放', released_at=CURRENT_TIMESTAMP WHERE instance_id=:id AND lock_status='占用中'"), {'id': instance['id']})
        conn.execute(text("""INSERT INTO workflow_audit_logs (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'执行完成',:worker,'执行中','已完成',:detail)"""), {'id': instance['id'], 'worker': worker_id, 'detail': _json({'count': len(serials), 'action': 'shipment-recall'})})
        conn.execute(text("""INSERT INTO workflow_outbox_events
            (instance_id,event_type,idempotency_key,payload)
            VALUES (:id,'逆向执行完成',:key,:payload)
            ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key"""),
            {'id': instance['id'], 'key': f"{instance_no}:completed", 'payload': _json({'workflow_key': instance['workflow_key'], 'count': len(serials)})})
        derived_tasks = create_reinbound_tasks(conn, instance, worker_id)
        if derived_tasks:
            conn.execute(text("UPDATE workflow_instances SET status='待派生处理' WHERE id=:id AND status='已完成'"), {'id': instance['id']})
        return {'instance_no': instance_no, 'status': '待派生处理' if derived_tasks else '已完成', 'count': len(serials), 'serials': serials, 'derived_tasks': derived_tasks}


def create_and_execute_shipment_recall(instance_no: str, worker_id: str):
    """Create and immediately run the shipment-recall child flow for shipped items."""
    ensure_workflow_tables()
    with get_engine().connect() as conn:
        parent = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no"), {'no': instance_no}).mappings().first()
        if not parent:
            raise ValueError('父流程不存在')
        rows = conn.execute(text("""SELECT object_id FROM workflow_instance_items
            WHERE instance_id=:id AND object_type='机台' ORDER BY object_id"""), {'id': parent['id']}).mappings().all()
        if rows:
            serials = [str(row['object_id']).strip() for row in rows]
        else:
            # Order/contract reverse flows store the business object itself;
            # derive the shipped machine serials for the shipment-recall child.
            column = '占用订单号' if parent['workflow_key'] == 'order-delete' else '合同号'
            shipped = conn.execute(text(f"""SELECT `流水号` FROM finished_goods_data
                WHERE TRIM(COALESCE(`{column}`,''))=:business_id
                  AND TRIM(COALESCE(`状态`,'')) IN ('已出库','已发货','库存中（DG-WH）')
                ORDER BY `流水号`"""), {'business_id': str(parent['business_id']).strip()}).mappings().all()
            serials = [str(row['流水号']).strip() for row in shipped]
        if not serials:
            raise ValueError('没有可发起发货撤回的机台')
        items = [{'object_type': '机台', 'object_id': serial} for serial in serials]
    child, _ = create_reverse_instance(
        workflow_key='shipment-recall', business_type='机台', business_id=str(parent['business_id']),
        operator_id=worker_id, idempotency_key=f'{instance_no}:shipment-recall',
        reason=f'由{parent["workflow_key"]}流程自动发起', items=items)
    acquire_execution_lease(child['instance_no'], worker_id)
    return execute_shipment_recall(child['instance_no'], worker_id)


def execute_customer_order_shipped(instance_no: str, worker_id: str):
    """Execute the model-selected shipping action with atomic workflow completion."""
    from api.routes.inventory import confirm_shipping, ShippingActionPayload
    with get_engine().connect() as conn:
        instance = conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no'), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'customer-order-shipped' or instance['status'] != '执行中':
            raise ValueError('客户成品发货流程当前不可执行')
        lease = conn.execute(text("SELECT * FROM workflow_execution_attempts WHERE instance_id=:id AND worker_id=:worker AND status='执行中' ORDER BY id DESC LIMIT 1"), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在')
        items = conn.execute(text('SELECT * FROM workflow_instance_items WHERE instance_id=:id'), {'id': instance['id']}).mappings().all()
        if not items or any(i['object_type'] != '机台' for i in items):
            raise ValueError('客户成品发货缺少机台明细')
    return {**confirm_shipping(ShippingActionPayload(serial_nos=[i['object_id'] for i in items], expected_order_no=instance['business_id']),
        None, worker_id, {'username': worker_id}, workflow_execution={
            'instance': dict(instance), 'lease': dict(lease), 'items': items, 'operator': worker_id}),
        'instance_no': instance_no, 'status': '已完成'}


def execute_customer_finished_recall(instance_no: str, worker_id: str):
    """Recall customer-finished-goods shipment and clear its acknowledgement plan."""
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE"), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'customer-finished-recall':
            raise ValueError('流程不存在或不是客户成品撤回流程')
        if instance['status'] != '执行中':
            raise ValueError(f'流程当前状态为{instance["status"]}，不能执行')
        lease = conn.execute(text("""SELECT * FROM workflow_execution_attempts WHERE instance_id=:id
            AND worker_id=:worker AND status='执行中' AND lease_expires_at > CURRENT_TIMESTAMP(6)
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在或已过期')
        _assert_lease_alive(conn, lease)
        items = conn.execute(text("SELECT * FROM workflow_instance_items WHERE instance_id=:id ORDER BY object_type, object_id FOR UPDATE"), {'id': instance['id']}).mappings().all()
        serials = [str(i['object_id']).strip() for i in items]
        if not serials or any(i['object_type'] not in ('机台', '客户成品') for i in items):
            raise ValueError('客户成品撤回流程缺少有效明细')
        placeholders = ','.join(f':sn{i}' for i in range(len(serials)))
        params = {f'sn{i}': sn for i, sn in enumerate(serials)}
        rows = conn.execute(text(f"SELECT `流水号`,`状态`,`占用订单号`,`Location_Code`,`row_version` FROM finished_goods_data WHERE TRIM(`流水号`) IN ({placeholders}) FOR UPDATE"), params).mappings().all()
        by_sn = {str(r['流水号']).strip(): r for r in rows}
        if len(by_sn) != len(set(serials)):
            raise ValueError('部分客户成品不存在，整单不执行')
        _validate_machine_snapshots(items, by_sn)
        invalid = [sn for sn in serials if str(by_sn[sn].get('状态') or '').strip() not in ('已发货', '已出库') and not (
            str(by_sn[sn].get('状态') or '').strip().startswith('库存中') and str(by_sn[sn].get('Location_Code') or '').strip() in {'DG-WH', 'DONGGUAN', '东莞仓库'})]
        if invalid:
            raise ValueError(f'客户成品当前不可撤回: {", ".join(invalid[:10])}')
        for sn in serials:
            _assert_lease_alive(conn, lease)
            changed = conn.execute(text("""UPDATE finished_goods_data SET `状态`='待入库', `Location_Code`='',
                `占用订单号`='', `客户`='', `代理商`='', `合同号`='', `更新时间`=CURRENT_TIMESTAMP, `row_version`=`row_version`+1
                WHERE TRIM(`流水号`)=:sn AND (`状态` IN ('已发货','已出库') OR (TRIM(`状态`) LIKE '库存中%' AND TRIM(COALESCE(`Location_Code`,'')) IN ('DG-WH','DONGGUAN','东莞仓库'))) AND `row_version`=:version"""), {'sn': sn, 'version': by_sn[sn].get('row_version') or 1})
            if changed.rowcount != 1:
                raise ValueError(f'客户成品 {sn} 状态并发变化，整单回滚')
            conn.execute(text("UPDATE customer_machine_plans SET plan_status='未核销', updated_at=CURRENT_TIMESTAMP WHERE TRIM(serial_no)=:sn"), {'sn': sn})
            conn.execute(text("UPDATE workflow_instance_items SET execution_result='已撤回' WHERE instance_id=:id AND object_id=:sn"), {'id': instance['id'], 'sn': sn})
        conn.execute(text("""UPDATE workflow_execution_attempts SET status='已完成', completed_at=CURRENT_TIMESTAMP(6), validation_result=:validation
            WHERE id=:attempt AND lease_token=:token AND status='执行中'"""), {'attempt': lease['id'], 'token': lease['lease_token'], 'validation': _json({'count': len(serials)})})
        conn.execute(text("UPDATE workflow_instances SET status='已完成', result='成功', executor_id=:worker, completed_at=CURRENT_TIMESTAMP WHERE id=:id AND status='执行中'"), {'worker': worker_id, 'id': instance['id']})
        conn.execute(text("UPDATE workflow_object_locks SET lock_status='已释放', released_at=CURRENT_TIMESTAMP WHERE instance_id=:id AND lock_status='占用中'"), {'id': instance['id']})
        conn.execute(text("""INSERT INTO workflow_audit_logs (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'执行完成',:worker,'执行中','已完成',:detail)"""), {'id': instance['id'], 'worker': worker_id, 'detail': _json({'count': len(serials), 'action': 'customer-finished-recall'})})
        conn.execute(text("""INSERT INTO workflow_outbox_events
            (instance_id,event_type,idempotency_key,payload)
            VALUES (:id,'逆向执行完成',:key,:payload)
            ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key"""),
            {'id': instance['id'], 'key': f"{instance_no}:completed", 'payload': _json({'workflow_key': instance['workflow_key'], 'count': len(serials)})})
        derived_tasks = create_reinbound_tasks(conn, instance, worker_id)
        if derived_tasks:
            conn.execute(text("UPDATE workflow_instances SET status='待派生处理' WHERE id=:id AND status='已完成'"), {'id': instance['id']})
        return {'instance_no': instance_no, 'status': '待派生处理' if derived_tasks else '已完成', 'count': len(serials), 'serials': serials, 'derived_tasks': derived_tasks}


def mark_execution_failure(instance_no: str, worker_id: str, error: str):
    """Close an execution attempt after its business transaction rolled back."""
    ensure_workflow_tables()
    message = (error or '未知执行异常')[:1000]
    with get_engine().begin() as conn:
        instance = conn.execute(text("SELECT id,status FROM workflow_instances WHERE instance_no=:no FOR UPDATE"),
                                 {'no': instance_no}).mappings().first()
        if not instance or instance['status'] != '执行中':
            return False
        attempt = conn.execute(text("""SELECT id FROM workflow_execution_attempts
            WHERE instance_id=:id AND worker_id=:worker AND status='执行中'
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""),
                                {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not attempt:
            return False
        conn.execute(text("""UPDATE workflow_execution_attempts
            SET status='执行异常', completed_at=CURRENT_TIMESTAMP(6), validation_result=:detail
            WHERE id=:attempt AND status='执行中'"""),
                     {'attempt': attempt['id'], 'detail': _json({'error': message})})
        conn.execute(text("""UPDATE workflow_instances
            SET status='执行异常', result='失败', failure_reason=:error
            WHERE id=:id AND status='执行中'"""),
                     {'id': instance['id'], 'error': message})
        conn.execute(text("""INSERT INTO workflow_audit_logs
            (instance_id,action,operator_id,before_state,after_state,detail)
            VALUES (:id,'执行异常',:worker,'执行中','执行异常',:detail)"""),
                     {'id': instance['id'], 'worker': worker_id, 'detail': _json({'error': message})})
        return True


_SPOT_ONLY_BATCHES = {'现货(spot)', '现货', 'spot', '库存中', 'finished-stock', '库存'}


def _rollback_unallocated_contracts(conn, order_id: str) -> list[str]:
    """把"已转订单但实际没占用任何机台"的合同恢复为待规划并解绑。

    判定口径：合同下没有已出库/已发货/库存中的机台，也没有任何 units 预占，
    且 `指定批次/来源` 为空或只写了"现货/库存"这类非生产批次。
    配现货本身不锁实物（真实占用一定落在 units / finished_goods_data 上），
    所以空壳单回滚是安全的；真正锁定了生产批次的合同（如 {"09-11": 1}）不动，需走撤销规划流程。

    调用前必须已经清空该订单的 finished_goods_data 占用与 units 绑定，否则 NOT EXISTS 不成立。
    返回被回滚的合同号列表。
    """
    candidates = conn.execute(text("""
        SELECT `合同号`, `指定批次/来源` FROM factory_plan
        WHERE TRIM(COALESCE(`订单号`, ''))=:oid
          AND TRIM(COALESCE(`状态`, ''))='已转订单'
          AND NOT EXISTS (
              SELECT 1 FROM finished_goods_data fg
              WHERE TRIM(COALESCE(fg.`合同号`, ''))=TRIM(COALESCE(factory_plan.`合同号`, ''))
                AND TRIM(COALESCE(fg.`状态`, '')) IN ('已出库', '已发货', '库存中')
          )
          AND NOT EXISTS (
              SELECT 1 FROM units u
              WHERE TRIM(COALESCE(u.contract_no, ''))=TRIM(COALESCE(factory_plan.`合同号`, ''))
                AND TRIM(COALESCE(u.status, '')) IN ('Confirmed', 'In_Production')
          )
    """), {'oid': order_id}).mappings().all()
    rollback_contract_ids = []
    for candidate in candidates:
        candidate_cid = str(candidate.get('合同号') or '').strip()
        raw_batch = candidate.get('指定批次/来源')
        if not candidate_cid:
            continue
        try:
            parsed_batch = json.loads(raw_batch) if isinstance(raw_batch, str) and raw_batch.strip() else (raw_batch or {})
        except (TypeError, ValueError):
            parsed_batch = None
        if parsed_batch is None:
            continue  # 批次内容解析不了就不动，留给人工确认
        if isinstance(parsed_batch, dict):
            batch_keys = []
            for key, value in parsed_batch.items():
                try:
                    if float(value or 0) <= 0:
                        continue
                except (TypeError, ValueError):
                    pass
                batch_keys.append(str(key).strip())
        elif isinstance(parsed_batch, list):
            batch_keys = [str(key).strip() for key in parsed_batch]
        else:
            batch_keys = []
        if all(key.lower() in _SPOT_ONLY_BATCHES for key in batch_keys):
            rollback_contract_ids.append(candidate_cid)
    if not rollback_contract_ids:
        return []
    conn.execute(text("""UPDATE factory_plan SET `状态`='待规划', `订单号`=NULL, `指定批次/来源`=NULL
        WHERE `合同号` COLLATE utf8mb4_general_ci IN :cids""").bindparams(
            bindparam('cids', expanding=True)), {'cids': rollback_contract_ids})
    if conn.execute(text("SHOW TABLES LIKE 'plan_import'")).first():
        try:
            conn.execute(text("""UPDATE plan_import SET `订单号`=NULL
                WHERE `合同号` COLLATE utf8mb4_general_ci IN :cids""").bindparams(
                    bindparam('cids', expanding=True)), {'cids': rollback_contract_ids})
        except Exception:
            pass
    return rollback_contract_ids


def _recompute_order_status_after_recall(conn, order_id: str) -> str | None:
    """撤回后按"实际还剩多少机台占用"重新判定订单状态。

    原来只写死 `status IN ('ready','allocated','packed')`，撤回发生在别的状态
    （如批次预占的 pending_review）时 UPDATE 命中 0 行，订单状态原地不动。
    这里改为看残留：没有任何机台/units 占用就回到 active，否则保持原状态不动。
    终态（deleted/done/shipped 等）一律不碰。
    """
    remaining_row = conn.execute(text("""
        SELECT COUNT(*) AS n FROM finished_goods_data
        WHERE TRIM(COALESCE(`占用订单号`, ''))=:oid
          AND TRIM(COALESCE(`状态`, '')) IN ('待发货', '机台')
    """), {'oid': order_id}).mappings().first()
    remaining = int((remaining_row or {}).get('n') or 0)
    if remaining == 0:
        remaining_row = conn.execute(text("""
            SELECT COUNT(*) AS n FROM units
            WHERE TRIM(COALESCE(sales_id, ''))=:oid
              AND TRIM(COALESCE(status, '')) IN ('Confirmed', 'In_Production')
        """), {'oid': order_id}).mappings().first()
        remaining = int((remaining_row or {}).get('n') or 0)
    if remaining:
        return None
    changed = conn.execute(text("""
        UPDATE sales_orders SET status='active'
        WHERE TRIM(COALESCE(`订单号`, ''))=:oid
          AND status IN ('ready', 'allocated', 'packed', 'pending_review')
    """), {'oid': order_id})
    return 'active' if changed.rowcount else None


def _clear_order_planning_caches():
    """订单/合同/库存读接口都有缓存，业务写完必须显式清，否则页面读到旧数据。"""
    try:
        from crud.orders import get_orders, get_orders_v2
        for _loader in (get_orders, get_orders_v2):
            if hasattr(_loader, 'cache_clear'):
                _loader.cache_clear()
    except Exception:
        pass
    try:
        from crud.planning import get_factory_plan, get_factory_plan_v2
        for _loader in (get_factory_plan, get_factory_plan_v2):
            if hasattr(_loader, 'cache_clear'):
                _loader.cache_clear()
    except Exception:
        pass


def execute_order_delete(instance_no: str, worker_id: str):
    """Soft-delete an order after approval and release only non-shipped allocations."""
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE"), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'order-delete':
            raise ValueError('流程不存在或不是订单删除流程')
        if instance['status'] != '执行中':
            raise ValueError(f'流程当前状态为{instance["status"]}，不能执行')
        lease = conn.execute(text("""SELECT * FROM workflow_execution_attempts WHERE instance_id=:id
            AND worker_id=:worker AND status='执行中' AND lease_expires_at > CURRENT_TIMESTAMP(6)
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在或已过期')
        _assert_lease_alive(conn, lease)
        order_id = str(instance['business_id']).strip()
        order = conn.execute(text("SELECT *, COALESCE(row_version, 1) AS _row_version FROM sales_orders WHERE `订单号`=:oid FOR UPDATE"), {'oid': order_id}).mappings().first()
        if not order:
            raise ValueError('订单不存在，不能删除')
        item_snapshot = conn.execute(text("SELECT before_state FROM workflow_instance_items WHERE instance_id=:id LIMIT 1"), {'id': instance['id']}).scalar()
        if item_snapshot:
            try:
                expected = json.loads(item_snapshot) if isinstance(item_snapshot, str) else item_snapshot
                if expected and (str(expected.get('status') or '') != str(order.get('status') or '') or
                                 str(expected.get('delete_reason') or '') != str(order.get('delete_reason') or '')):
                    raise ValueError('订单审批后状态已变化，不能执行')
            except ValueError:
                raise
            except Exception:
                pass
        shipped = conn.execute(text("""SELECT COUNT(*) FROM finished_goods_data
            WHERE TRIM(`占用订单号`)=:oid AND TRIM(COALESCE(`状态`,'')) IN ('已出库','已发货','库存中（DG-WH）')"""), {'oid': order_id}).scalar()
        if int(shipped or 0) > 0:
            raise ValueError('订单存在已发货机台，不能删除')
        reinbound_object_ids = [str(row[0]).strip() for row in conn.execute(text("""SELECT `流水号`
            FROM finished_goods_data
            WHERE TRIM(`占用订单号`)=:oid
              AND TRIM(COALESCE(`状态`,'')) IN ('待发货','机台')"""), {'oid': order_id}).fetchall()
            if str(row[0] or '').strip()]
        conn.execute(text("""UPDATE finished_goods_data SET `状态`='待入库', `占用订单号`='',
            `合同号`='', `客户`='', `代理商`='', `更新时间`=CURRENT_TIMESTAMP
            WHERE TRIM(`占用订单号`)=:oid AND TRIM(COALESCE(`状态`,'')) IN ('待发货','机台')"""), {'oid': order_id})
        # 同步释放沙盘 units 上的预占：只清 finished_goods_data 会让订单进度仍把这批在产机台
        # 算成"已配"，删除后订单在配货页继续显示"待发货"，机台也无法被其他订单使用。
        conn.execute(text("""UPDATE units SET contract_no=NULL, customer=NULL, dealer_name=NULL,
            sales_id=NULL, due_date=NULL, is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
            WHERE TRIM(COALESCE(sales_id, ''))=:oid"""), {'oid': order_id})
        # 订单删除后，把"已转订单但实际没有占用任何机台"的合同恢复为待规划并解绑，
        # 否则合同会永久停在已转订单、绑定一个已删除订单：既不能再做批次规划，也不能取消。
        _rollback_unallocated_contracts(conn, order_id)
        changed = conn.execute(text("UPDATE sales_orders SET status='deleted', delete_reason=:reason, row_version=COALESCE(row_version, 1)+1 WHERE `订单号`=:oid AND COALESCE(row_version, 1)=:version"),
                     {'oid': order_id, 'reason': f'逆向审批删除:{instance_no}', 'version': order['_row_version']})
        if changed.rowcount != 1:
            raise ValueError('订单版本并发变化，整单回滚')
        conn.execute(text("UPDATE workflow_instance_items SET execution_result='已删除' WHERE instance_id=:id"), {'id': instance['id']})
        path_log = conn.execute(text("""SELECT detail FROM workflow_audit_logs
            WHERE instance_id=:id AND action='模型路径推进' ORDER BY id DESC LIMIT 1"""), {'id': instance['id']}).scalar()
        try:
            path_result = json.loads(path_log) if isinstance(path_log, str) else (path_log or {})
        except (TypeError, ValueError):
            path_result = {}
        use_reinbound = 'delete_order_reinbound' in (path_result.get('executed_actions') or [])
        _finish_reverse_execution(conn, instance, lease, worker_id,
                                  {'workflow_key': 'order-delete', 'business_id': order_id},
                                  force_reinbound=use_reinbound,
                                  reinbound_object_ids=reinbound_object_ids)
    # Clear only after commit, so readers cannot refill caches from pre-delete data.
    _clear_order_planning_caches()
    return {'instance_no': instance_no, 'status': '已完成', 'business_id': order_id}


def execute_model_dict_delete(instance_no: str, worker_id: str):
    """Disable a model dictionary entry after approval (logical deletion)."""
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE"), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'model-dict-delete':
            raise ValueError('流程不存在或不是机型字典删除流程')
        if instance['status'] != '执行中':
            raise ValueError(f'流程当前状态为{instance["status"]}，不能执行')
        lease = conn.execute(text("""SELECT * FROM workflow_execution_attempts WHERE instance_id=:id
            AND worker_id=:worker AND status='执行中' AND lease_expires_at > CURRENT_TIMESTAMP(6)
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在或已过期')
        _assert_lease_alive(conn, lease)
        raw = str(instance['business_id']).strip()
        try:
            id_value = int(raw)
        except ValueError:
            id_value = None
        if id_value is not None:
            row = conn.execute(text("SELECT *, COALESCE(row_version, 1) AS _row_version FROM model_dictionary WHERE id=:id FOR UPDATE"), {'id': id_value}).mappings().first()
            where = 'id=:id'; params = {'id': id_value}
        else:
            row = conn.execute(text("SELECT *, COALESCE(row_version, 1) AS _row_version FROM model_dictionary WHERE model_name=:name FOR UPDATE"), {'name': raw}).mappings().first()
            where = 'model_name=:name'; params = {'name': raw}
        if not row:
            raise ValueError('机型不存在，不能删除')
        item_snapshot = conn.execute(text("SELECT before_state FROM workflow_instance_items WHERE instance_id=:id LIMIT 1"), {'id': instance['id']}).scalar()
        if item_snapshot:
            try:
                expected = json.loads(item_snapshot) if isinstance(item_snapshot, str) else item_snapshot
                if expected and (str(expected.get('model_name') or '') != str(row.get('model_name') or '') or
                                 int(expected.get('enabled', 0)) != int(row.get('enabled', 0))):
                    raise ValueError('机型审批后状态已变化，不能执行')
            except ValueError:
                raise
            except Exception:
                pass
        enabled_count = conn.execute(text("SELECT COUNT(*) FROM model_dictionary WHERE enabled=1")).scalar()
        if int(enabled_count or 0) <= 1 and int(row.get('enabled') or 0) == 1:
            raise ValueError('至少保留一个启用机型')
        params = {**params, 'version': row.get('_row_version') or 1}
        changed = conn.execute(text(f"UPDATE model_dictionary SET enabled=0, row_version=COALESCE(row_version, 1)+1 WHERE {where} AND COALESCE(row_version, 1)=:version"), params)
        if changed.rowcount != 1:
            raise ValueError('机型状态并发变化，整单回滚')
        conn.execute(text("UPDATE workflow_instance_items SET execution_result='已删除' WHERE instance_id=:id"), {'id': instance['id']})
        _finish_reverse_execution(conn, instance, lease, worker_id, {'workflow_key': 'model-dict-delete', 'business_id': raw})
        return {'instance_no': instance_no, 'status': '已完成', 'business_id': raw}


def execute_contract_cancel(instance_no: str, worker_id: str):
    """Cancel a contract and release its planning/inventory references atomically."""
    ensure_workflow_tables()
    with get_engine().begin() as conn:
        instance = conn.execute(text("SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE"), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'contract-cancel':
            raise ValueError('流程不存在或不是合同撤销流程')
        if instance['status'] != '执行中':
            raise ValueError(f'流程当前状态为{instance["status"]}，不能执行')
        lease = conn.execute(text("""SELECT * FROM workflow_execution_attempts WHERE instance_id=:id
            AND worker_id=:worker AND status='执行中' AND lease_expires_at > CURRENT_TIMESTAMP(6)
            ORDER BY id DESC LIMIT 1 FOR UPDATE"""), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在或已过期')
        _assert_lease_alive(conn, lease)
        contract_no = str(instance['business_id']).strip()
        plan_count = conn.execute(text("SELECT COUNT(*) FROM factory_plan WHERE TRIM(`合同号`)=:cid"), {'cid': contract_no}).scalar()
        # A contract without a planning row can be cancelled after approval
        # only when it has no downstream business binding.
        item_snapshot = conn.execute(text("SELECT before_state FROM workflow_instance_items WHERE instance_id=:id LIMIT 1"), {'id': instance['id']}).scalar()
        if item_snapshot:
            try:
                expected = json.loads(item_snapshot) if isinstance(item_snapshot, str) else item_snapshot
                current_statuses = conn.execute(text("SELECT GROUP_CONCAT(DISTINCT COALESCE(`状态`, '') ORDER BY `状态`) FROM factory_plan WHERE TRIM(`合同号`)=:cid"), {'cid': contract_no}).scalar() or ''
                if expected and (int(expected.get('plan_count') or 0) != int(plan_count) or str(expected.get('statuses') or '') != str(current_statuses)):
                    raise ValueError('合同审批后计划状态已变化，不能执行')
            except ValueError:
                raise
            except Exception:
                pass
        downstream = conn.execute(text("""SELECT
            (SELECT COUNT(*) FROM sales_orders so WHERE EXISTS
                (SELECT 1 FROM factory_plan fp WHERE TRIM(COALESCE(fp.`合同号`,''))=:cid
                 AND TRIM(COALESCE(fp.`订单号`,''))=TRIM(so.`订单号`))) AS order_count,
            (SELECT COUNT(*) FROM finished_goods_data WHERE TRIM(COALESCE(`合同号`,''))=:cid) AS machine_count,
            (SELECT COUNT(*) FROM rush_order_queue WHERE TRIM(COALESCE(contract_no,''))=:cid AND status NOT IN ('deleted','cancelled')) AS rush_count,
            (SELECT COUNT(*) FROM production_queue WHERE TRIM(COALESCE(contract_no,''))=:cid AND status NOT IN ('Pulled','Cancelled')) AS queue_count"""), {'cid': contract_no}).mappings().first()
        if int(plan_count or 0) == 0 and any(int(downstream.get(key) or 0) for key in ('order_count', 'machine_count', 'rush_count', 'queue_count')):
            raise ValueError('未规划合同存在订单、机台或排产关联，不能直接自动取消')
        # Shipped goods are immutable; cancel only unshipped planning/inventory links.
        shipped = conn.execute(text("""SELECT COUNT(*) FROM finished_goods_data
            WHERE TRIM(`合同号`)=:cid AND TRIM(COALESCE(`状态`,'')) IN ('已出库','已发货','库存中（DG-WH）')"""), {'cid': contract_no}).scalar()
        if int(shipped or 0) > 0:
            raise ValueError('合同存在已发货机台，不能撤销')
        conn.execute(text("""UPDATE finished_goods_data SET `合同号`='', `占用订单号`='', `客户`='', `代理商`='',
            `状态`='待入库', `更新时间`=CURRENT_TIMESTAMP, `row_version`=COALESCE(row_version,1)+1
            WHERE TRIM(`合同号`)=:cid"""), {'cid': contract_no})
        conn.execute(text("UPDATE units SET contract_no=NULL, is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW() WHERE contract_no=:cid"), {'cid': contract_no})
        conn.execute(text("UPDATE factory_plan SET `状态`='已取消', `订单号`=NULL WHERE TRIM(`合同号`)=:cid"), {'cid': contract_no})
        conn.execute(text("UPDATE rush_order_queue SET status='deleted', updated_at=CURRENT_TIMESTAMP WHERE contract_no=:cid AND status='pending'"), {'cid': contract_no})
        conn.execute(text("UPDATE production_queue SET quantity_remaining=0, status='Pulled' WHERE contract_no=:cid AND status='Waiting'"), {'cid': contract_no})
        conn.execute(text("UPDATE workflow_instance_items SET execution_result='已撤销' WHERE instance_id=:id"), {'id': instance['id']})
        path_log = conn.execute(text("""SELECT detail FROM workflow_audit_logs
            WHERE instance_id=:id AND action='模型路径推进' ORDER BY id DESC LIMIT 1"""), {'id': instance['id']}).scalar()
        try:
            path_result = json.loads(path_log) if isinstance(path_log, str) else (path_log or {})
        except (TypeError, ValueError):
            path_result = {}
        use_reinbound = 'cancel_contract_reinbound' in (path_result.get('executed_actions') or [])
        _finish_reverse_execution(conn, instance, lease, worker_id, {'workflow_key': 'contract-cancel', 'business_id': contract_no}, force_reinbound=use_reinbound)
        return {'instance_no': instance_no, 'status': '已完成', 'business_id': contract_no}


def _finish_reverse_execution(conn, instance, lease, worker_id, payload, force_reinbound: bool | None = None,
                              reinbound_object_ids: list[str] | None = None):
    derived_tasks = create_reinbound_tasks(conn, instance, worker_id, force=force_reinbound,
                                           object_ids=reinbound_object_ids)
    final_status = '待派生处理' if derived_tasks else '已完成'
    conn.execute(text("""UPDATE workflow_execution_attempts SET status='已完成', completed_at=CURRENT_TIMESTAMP(6), validation_result=:validation
        WHERE id=:attempt AND lease_token=:token AND status='执行中'"""), {'attempt': lease['id'], 'token': lease['lease_token'], 'validation': _json(payload)})
    conn.execute(text("""UPDATE workflow_instances SET status=:status, result='成功', executor_id=:worker,
        completed_at=CASE WHEN :status='已完成' THEN CURRENT_TIMESTAMP ELSE NULL END
        WHERE id=:id AND status='执行中'"""), {'status': final_status, 'worker': worker_id, 'id': instance['id']})
    conn.execute(text("UPDATE workflow_object_locks SET lock_status='已释放', released_at=CURRENT_TIMESTAMP WHERE instance_id=:id AND lock_status='占用中'"""), {'id': instance['id']})
    conn.execute(text("""INSERT INTO workflow_audit_logs (instance_id,action,operator_id,before_state,after_state,detail)
        VALUES (:id,'执行完成',:worker,'执行中',:after_state,:detail)"""), {'id': instance['id'], 'worker': worker_id, 'after_state': final_status, 'detail': _json({**payload, 'derived_tasks': derived_tasks})})
    conn.execute(text("""INSERT INTO workflow_outbox_events (instance_id,event_type,idempotency_key,payload)
        VALUES (:id,'逆向执行完成',:key,:payload) ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key"""),
                 {'id': instance['id'], 'key': f"{instance['instance_no']}:completed", 'payload': _json({**payload, 'derived_tasks': derived_tasks})})


def forward_workflow_enabled(workflow_key: str) -> bool:
    raw = os.getenv('WORKFLOW_FORWARD_ENABLED', '').strip().lower()
    keys = {x.strip() for x in os.getenv('WORKFLOW_FORWARD_KEYS', '').split(',') if x.strip()}
    return raw in {'1', 'true', 'yes', 'on'} and (not keys or workflow_key in keys)


def record_forward_instance(workflow_key: str, business_type: str, business_id: str,
                            operator: str, idempotency_key: str, batch_no: str = '',
                            request_id: str = '', before_state=None, target_state=None, conn=None):
    """记录自动通过流程。默认关闭，失败时返回 None，不影响旧业务入口。"""
    from crud.forward_entries import replaying
    if replaying() or not forward_workflow_enabled(workflow_key):
        return None
    ensure_workflow_tables()
    instance_no = f'WF-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:10].upper()}'
    def _record(active_conn):
        model = active_conn.execute(text("""SELECT m.id, v.id AS version_id FROM workflow_models m
            JOIN workflow_model_versions v ON v.model_id=m.id AND v.version_no=m.current_version
            WHERE m.workflow_key=:key AND m.status='已发布' AND v.status='已发布' LIMIT 1"""), {'key': workflow_key}).mappings().first()
        if not model:
            raise RuntimeError(f'流程模型不可用: {workflow_key}')
        existing = active_conn.execute(text('SELECT * FROM workflow_instances WHERE idempotency_key=:k'), {'k': idempotency_key}).mappings().first()
        if existing:
            return dict(existing)
        active_conn.execute(text("""INSERT INTO workflow_instances
            (instance_no,workflow_key,model_version_id,request_id,batch_no,idempotency_key,
             business_type,business_id,before_state_snapshot,target_state_snapshot,status,
             initiator_id,executor_id,result,completed_at)
            VALUES (:no,:key,:version,:request,:batch,:idem,:bt,:bid,:before,:target,
                    '已完成',:operator,:operator,'成功',CURRENT_TIMESTAMP)"""), {
            'no': instance_no, 'key': workflow_key, 'version': model['version_id'],
            'request': request_id, 'batch': batch_no, 'idem': idempotency_key,
            'bt': business_type, 'bid': business_id, 'before': _json(before_state),
            'target': _json(target_state), 'operator': operator,
        })
        instance = active_conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no'), {'no': instance_no}).mappings().first()
        active_conn.execute(text("""INSERT INTO workflow_tasks
            (instance_id,node_type,node_order,assignee_id,status,decision,completed_at)
            VALUES (:id,'自动通过',1,:operator,'已结束','通过',CURRENT_TIMESTAMP)"""),
            {'id': instance['id'], 'operator': 'system'})
        return dict(instance)
    try:
        if conn is None:
            with get_engine().begin() as active_conn:
                return _record(active_conn)
        return _record(conn)
    except Exception as exc:
        # A legacy or isolated test database may not have workflow tables yet.
        # Forward recording must not block the already successful business action.
        message = str(exc).lower()
        if "no such table" in message or "doesn't exist" in message or "unknown table" in message:
            return None
        raise


def claim_outbox_events(worker_id: str, limit: int = 20):
    """Atomically claim pending outbox events for a worker."""
    ensure_workflow_tables()
    limit = max(1, min(int(limit), 100))
    with get_engine().begin() as conn:
        rows = conn.execute(text(f"""SELECT * FROM workflow_outbox_events
            WHERE status IN ('待发送','重试中')
              AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
            ORDER BY id LIMIT {limit} FOR UPDATE SKIP LOCKED""")).mappings().all()
        claimed = []
        for row in rows:
            conn.execute(text("""UPDATE workflow_outbox_events SET status='处理中', failure_reason=NULL
                WHERE id=:id AND status IN ('待发送','重试中')"""), {'id': row['id']})
            claimed.append(dict(row))
        return claimed


def complete_outbox_event(event_id: int):
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE workflow_outbox_events SET status='已发送' WHERE id=:id AND status='处理中'"), {'id': int(event_id)})


def fail_outbox_event(event_id: int, error: str, retry_seconds: int = 60, max_retries: int = 8):
    with get_engine().begin() as conn:
        conn.execute(text("""UPDATE workflow_outbox_events
            SET status=CASE WHEN retry_count+1 >= :max_retries THEN '永久失败待处理' ELSE '重试中' END,
                retry_count=retry_count+1, failure_reason=:error,
                next_retry_at=CASE WHEN retry_count+1 >= :max_retries THEN NULL
                    ELSE DATE_ADD(CURRENT_TIMESTAMP, INTERVAL :seconds SECOND) END
            WHERE id=:id AND status='处理中'"""),
                     {'id': int(event_id), 'error': str(error)[:1000], 'seconds': max(1, int(retry_seconds)),
                      'max_retries': max(1, int(max_retries))})


def requeue_outbox_event(event_id: int):
    with get_engine().begin() as conn:
        changed = conn.execute(text("""UPDATE workflow_outbox_events
            SET status='重试中', next_retry_at=CURRENT_TIMESTAMP, failure_reason=NULL
            WHERE id=:id AND status='永久失败待处理'"""), {'id': int(event_id)})
        if changed.rowcount != 1:
            raise ValueError('事件不存在或当前不可重新入队')


def reclaim_expired_execution_leases(limit: int = 100):
    ensure_workflow_tables()
    limit = max(1, min(int(limit), 500))
    with get_engine().begin() as conn:
        rows = conn.execute(text(f"""SELECT a.id,a.instance_id,i.instance_no FROM workflow_execution_attempts a
            JOIN workflow_instances i ON i.id=a.instance_id
            WHERE a.status='执行中' AND a.lease_expires_at <= CURRENT_TIMESTAMP(6)
            ORDER BY a.id LIMIT {limit} FOR UPDATE""")).mappings().all()
        for row in rows:
            conn.execute(text("UPDATE workflow_execution_attempts SET status='执行异常', completed_at=CURRENT_TIMESTAMP(6), failure_reason='执行租约已过期' WHERE id=:id AND status='执行中'"), {'id': row['id']})
            conn.execute(text("UPDATE workflow_instances SET status='执行异常', result='失败', failure_reason='执行租约已过期' WHERE id=:id AND status='执行中'"), {'id': row['instance_id']})
            conn.execute(text("""INSERT INTO workflow_audit_logs (instance_id,action,operator_id,before_state,after_state,detail)
                VALUES (:id,'租约回收','system','执行中','执行异常',:detail)"""), {'id': row['instance_id'], 'detail': _json({'reason': 'lease_expired'})})
        return [dict(row) for row in rows]

def publish_workflow_model(workflow_key: str, snapshot: dict, operator_id: str):
    ensure_workflow_tables()
    validate_workflow_snapshot(snapshot, workflow_key)
    with get_engine().begin() as conn:
        model = conn.execute(text('SELECT * FROM workflow_models WHERE workflow_key=:key FOR UPDATE'), {'key': workflow_key}).mappings().first()
        if not model:
            raise ValueError('流程模型不存在')
        next_version = int(conn.execute(text('SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=:id'), {'id': model['id']}).scalar() or 1)
        processing_type = '需要审批' if _snapshot_requires_approval(snapshot) else '自动通过'
        conn.execute(text("UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=:id AND status='已发布'"), {'id': model['id']})
        conn.execute(text("INSERT INTO workflow_model_versions (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at) VALUES (:id,:v,'已发布',:snapshot,1,:operator,CURRENT_TIMESTAMP)"), {'id': model['id'], 'v': next_version, 'snapshot': _json(snapshot), 'operator': operator_id})
        conn.execute(text("UPDATE workflow_models SET current_version=:v,status='已发布',processing_type=:processing,updated_by=:operator WHERE id=:id"), {'v': next_version, 'processing': processing_type, 'operator': operator_id, 'id': model['id']})
        conn.execute(text("DELETE FROM workflow_model_versions WHERE model_id=:id AND status='草稿'"), {'id': model['id']})
        return {'workflow_key': workflow_key, 'version': next_version, 'status': '已发布'}

def save_workflow_draft(workflow_key: str, snapshot: dict, operator_id: str):
    ensure_workflow_tables()
    validate_workflow_snapshot(snapshot, workflow_key)
    with get_engine().begin() as conn:
        model = conn.execute(text('SELECT id,current_version FROM workflow_models WHERE workflow_key=:key FOR UPDATE'), {'key': workflow_key}).mappings().first()
        if not model or not model['current_version']:
            raise ValueError('流程模型尚未初始化版本')
        draft = conn.execute(text("SELECT id FROM workflow_model_versions WHERE model_id=:id AND status='草稿' LIMIT 1 FOR UPDATE"), {'id': model['id']}).first()
        if draft:
            conn.execute(text("UPDATE workflow_model_versions SET node_snapshot=:snapshot,published_by=:operator WHERE id=:id"), {'snapshot': _json(snapshot), 'operator': operator_id, 'id': draft[0]})
        else:
            conn.execute(text("INSERT INTO workflow_model_versions (model_id,version_no,status,node_snapshot,runtime_enabled,published_by) VALUES (:id,:version,'草稿',:snapshot,0,:operator)"), {'id': model['id'], 'version': int(model['current_version']) + 1, 'snapshot': _json(snapshot), 'operator': operator_id})
        return {'workflow_key': workflow_key, 'version': model['current_version'], 'status': '草稿已保存'}


def execute_customer_machine_plan(instance_no: str, worker_id: str):
    from sqlalchemy import bindparam
    from api.routes.inventory import CustomerMachinePlanPayload, persist_customer_machine_plans, ensure_customer_plan_table
    ensure_customer_plan_table()
    with get_engine().begin() as conn:
        instance = conn.execute(text('SELECT * FROM workflow_instances WHERE instance_no=:no FOR UPDATE'), {'no': instance_no}).mappings().first()
        if not instance or instance['workflow_key'] != 'customer-machine-plan' or instance['status'] != '执行中':
            raise ValueError('规划流程当前不可执行')
        lease = conn.execute(text("SELECT * FROM workflow_execution_attempts WHERE instance_id=:id AND worker_id=:worker AND status='执行中' ORDER BY id DESC LIMIT 1 FOR UPDATE"), {'id': instance['id'], 'worker': worker_id}).mappings().first()
        if not lease:
            raise ValueError('执行租约不存在')
        _assert_lease_alive(conn, lease)
        raw = instance['target_state_snapshot']
        payload = CustomerMachinePlanPayload.model_validate(json.loads(raw) if isinstance(raw, str) else raw)
        items = conn.execute(text('SELECT * FROM workflow_instance_items WHERE instance_id=:id'), {'id': instance['id']}).mappings().all()
        serials = sorted({str(i['object_id']).strip() for i in items if i['object_type'] == '机台'})
        if not serials or len(serials) != len(items) or serials != sorted(set(payload.serial_nos)):
            raise ValueError('规划内容与流程机台明细不一致')
        rows = conn.execute(text('SELECT * FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE').bindparams(bindparam('sns', expanding=True)), {'sns': serials}).mappings().all()
        _validate_machine_snapshots(items, {str(r['流水号']).strip(): r for r in rows})
        persist_customer_machine_plans(conn, payload, instance['initiator_id'])
        _finish_reverse_execution(conn, instance, lease, worker_id, {'serial_nos': serials}, force_reinbound=False)
    return {'instance_no': instance_no, 'status': '已完成'}
