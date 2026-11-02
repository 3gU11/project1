"""Personal workflow inbox. All source queries are restricted to the signed-in user."""
from sqlalchemy import text
from database import get_engine


SOURCE = """
SELECT CONCAT('task:',t.id,':',t.status) message_key,
 CONCAT('待审批 · ', COALESCE(m.name, i.workflow_key)) title,
 CONCAT(COALESCE(NULLIF(TRIM(i.business_type),''),'事项'), ' ', i.business_id, ' 等待你审批') content,
 t.assigned_at event_at, '/approval-center' target
 FROM workflow_tasks t JOIN workflow_instances i ON i.id=t.instance_id
 LEFT JOIN workflow_models m ON m.workflow_key=i.workflow_key
 WHERE t.assignee_id=:username AND t.status='待处理' AND i.status='审批中'
UNION ALL
-- 发起人只看关键节点：审批通过 / 拒绝 / 完成 / 失败。
-- 1) 审批中、待派生处理属于过程态，不推；
-- 2) 正向流程（下单、配货、发货）成功是当场可见的，只在失败时提醒；
-- 3) 逆向流程（撤回、删单、取消）才推完整结果。
SELECT CONCAT('instance:',i.id,':',i.status) message_key,
 CONCAT(CASE i.status WHEN '已通过' THEN '审批已通过' WHEN '已拒绝' THEN '审批被拒绝'
                      WHEN '已完成' THEN '流程已完成' WHEN '执行异常' THEN '执行失败'
                      ELSE i.status END, ' · ', COALESCE(m.name, i.workflow_key)) title,
 CONCAT(COALESCE(NULLIF(TRIM(i.business_type),''),'事项'), ' ', i.business_id,
        CASE i.status
          WHEN '已通过' THEN ' 审批通过，正在执行'
          WHEN '已拒绝' THEN ' 审批未通过'
          WHEN '执行异常' THEN ' 处理失败，请联系管理员'
          WHEN '已完成' THEN CASE WHEN EXISTS (SELECT 1 FROM workflow_derived_tasks d WHERE d.instance_id=i.id)
                                  THEN ' 重入库已完成，流程结束' ELSE ' 处理完毕' END
          ELSE '' END) content,
 COALESCE(i.completed_at,i.created_at) event_at, '/approval-center' target
 FROM workflow_instances i
 LEFT JOIN workflow_models m ON m.workflow_key=i.workflow_key
 WHERE i.initiator_id=:username
   AND (i.status='执行异常'
        OR (COALESCE(m.direction,'正向')='逆向' AND i.status IN ('已通过','已拒绝','已完成')))
UNION ALL
SELECT CONCAT('derived:',d.id,':',d.status) message_key,
 CONCAT(CASE WHEN d.task_type='重入库' THEN '待重入库' ELSE CONCAT('待', d.task_type) END,
        CASE WHEN m.name IS NULL THEN '' ELSE CONCAT(' · ', m.name) END) title,
 CASE WHEN d.task_type='重入库' THEN CONCAT('机台 ', d.object_id, ' 需要重新入库')
      ELSE CONCAT('请处理', d.task_type, '：', d.object_id) END content,
 COALESCE(d.completed_at,d.created_at) event_at, '/inbound' target
 FROM workflow_derived_tasks d
 LEFT JOIN workflow_instances i ON i.id=d.instance_id
 LEFT JOIN workflow_models m ON m.workflow_key=i.workflow_key
 WHERE d.assignee_id=:username AND d.status='待处理'
UNION ALL
SELECT CONCAT('notice:',n.id), n.title, n.content, n.created_at, ''
 FROM workflow_notifications n WHERE n.recipient_id=:username
   AND n.notification_type <> '重入库'  -- 重入库已由派生任务条目承载，避免同一条消息出现两次
"""


def ensure_message_reads():
    with get_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS personal_message_reads (
            username VARCHAR(100) NOT NULL, message_key VARCHAR(180) NOT NULL,
            read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(username,message_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""))


def inbox(username, page=1, limit=20, unread=False):
    params = dict(username=username, limit=limit, offset=(page-1)*limit)
    base = f" FROM ({SOURCE}) n LEFT JOIN personal_message_reads r ON r.username=:username AND r.message_key=n.message_key"
    with get_engine().connect() as conn:
        count = conn.execute(text('SELECT COUNT(*)'+base+' WHERE r.message_key IS NULL'),params).scalar_one()
        where = ' WHERE r.message_key IS NULL' if unread else ''
        total = conn.execute(text('SELECT COUNT(*)'+base+where),params).scalar_one()
        rows = conn.execute(text('SELECT n.*, (r.message_key IS NULL) AS unread'+base+where+
                                 ' ORDER BY event_at DESC, n.message_key DESC LIMIT :limit OFFSET :offset'),params).mappings().all()
    return dict(data=[dict(row) for row in rows],total=total,unread_count=count,page=page,limit=limit)


def read_messages(username, message_key=None):
    # INSERT ... SELECT rechecks ownership; arbitrary message keys cannot be marked.
    where = ' WHERE n.message_key=:key' if message_key else ''
    with get_engine().begin() as conn:
        conn.execute(text(f"""INSERT IGNORE INTO personal_message_reads(username,message_key)
            SELECT :username,n.message_key FROM ({SOURCE}) n{where}"""),
            dict(username=username,key=message_key))
