"""Personal workflow inbox. All source queries are restricted to the signed-in user."""
from sqlalchemy import text
from database import get_engine


SOURCE = """
SELECT CONCAT('task:',t.id,':',t.status) message_key, '待我审批' title,
 CONCAT(i.business_id,' · ',i.workflow_key) content, t.assigned_at event_at,
 '/approval-center' target
 FROM workflow_tasks t JOIN workflow_instances i ON i.id=t.instance_id
 WHERE t.assignee_id=:username AND t.status='待处理' AND i.status='审批中'
UNION ALL
SELECT CONCAT('instance:',id,':',status), CONCAT('流程',status),
 CONCAT(business_id,' · ',workflow_key,' · ',instance_no),
 COALESCE(completed_at,created_at), '/approval-center'
 FROM workflow_instances WHERE initiator_id=:username
UNION ALL
SELECT CONCAT('derived:',id,':',status), CONCAT(task_type,'任务 · ',status),
 CONCAT(object_id,' · ',task_no), COALESCE(completed_at,created_at), '/inbound'
 FROM workflow_derived_tasks WHERE assignee_id=:username
UNION ALL
SELECT CONCAT('notice:',id),title,content,created_at,''
 FROM workflow_notifications WHERE recipient_id=:username
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
