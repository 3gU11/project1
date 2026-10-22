from sqlalchemy import create_engine, text

from crud.workflows import complete_reinbound_tasks_for_machine


def test_inbound_closes_all_older_tasks_without_closing_other_machines():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        for ddl in [
            'CREATE TABLE workflow_derived_tasks(id INTEGER,instance_id INTEGER,task_no TEXT,object_id TEXT,task_type TEXT,status TEXT,completed_by TEXT,completed_at TEXT,notification_status TEXT)',
            'CREATE TABLE workflow_notifications(reference_no TEXT,status TEXT,read_at TEXT)',
            'CREATE TABLE workflow_audit_logs(instance_id INTEGER,action TEXT,operator_id TEXT,before_state TEXT,after_state TEXT,detail TEXT)',
            'CREATE TABLE workflow_instances(id INTEGER,status TEXT,completed_at TEXT)',
        ]:
            db.execute(text(ddl))
        for task_id, parent, serial in [(1, 10, 'SN'), (2, 20, 'SN'), (3, 20, 'OTHER')]:
            db.execute(text("INSERT INTO workflow_derived_tasks(id,instance_id,task_no,object_id,task_type,status) VALUES (:id,:parent,:no,:sn,'重入库','待处理')"), {'id': task_id, 'parent': parent, 'no': str(task_id), 'sn': serial})
        db.execute(text("INSERT INTO workflow_instances VALUES (10,'待派生处理',NULL),(20,'待派生处理',NULL)"))
        db.execute(text("INSERT INTO workflow_notifications VALUES ('1','未读',NULL),('3','未读',NULL)"))

        class Connection:
            def execute(self, query, params):
                return db.execute(text(str(query).replace(' FOR UPDATE', '')), params)

        assert complete_reinbound_tasks_for_machine(Connection(), 'SN', 'inbound') == 2
        assert complete_reinbound_tasks_for_machine(Connection(), 'SN', 'inbound') == 0
        assert db.execute(text('SELECT status FROM workflow_derived_tasks ORDER BY id')).scalars().all() == ['已完成', '已完成', '待处理']
        assert db.execute(text('SELECT status FROM workflow_instances ORDER BY id')).scalars().all() == ['已完成', '待派生处理']
        assert db.execute(text("SELECT status FROM workflow_notifications WHERE reference_no='1'")).scalar() == '已读'
        assert db.execute(text('SELECT COUNT(*) FROM workflow_audit_logs')).scalar() == 2
