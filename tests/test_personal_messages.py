import unittest
from unittest.mock import patch
from sqlalchemy import create_engine,text
from crud.personal_messages import inbox

class PersonalInboxTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        with self.engine.begin() as c:
            c.connection.driver_connection.create_function('CONCAT',-1,lambda *v: ''.join(str(x or '') for x in v))
            for ddl in [
                'workflow_instances (id integer,instance_no text,workflow_key text,business_id text,status text,initiator_id text,created_at text,completed_at text)',
                'workflow_tasks (id integer,instance_id integer,status text,assignee_id text,assigned_at text)',
                'workflow_derived_tasks (id integer,status text,task_type text,object_id text,task_no text,assignee_id text,created_at text,completed_at text)',
                'workflow_notifications (id integer,title text,content text,recipient_id text,created_at text)',
                'personal_message_reads (username text,message_key text)']:
                c.execute(text('CREATE TABLE '+ddl))
            c.execute(text("INSERT INTO workflow_instances VALUES (1,'WF1','delete','SO1','审批中','sales','2026-10-19',NULL)"))
            c.execute(text("INSERT INTO workflow_tasks VALUES (1,1,'待处理','boss','2026-10-19')"))
            c.execute(text("INSERT INTO workflow_notifications VALUES (1,'私信','内容','inbound','2026-10-19')"))
        self.mock=patch('crud.personal_messages.get_engine',return_value=self.engine);self.mock.start()
    def tearDown(self):
        self.mock.stop();self.engine.dispose()
    def test_recipients_and_pagination(self):
        self.assertEqual(inbox('stranger')['total'],0)
        self.assertEqual(inbox('sales')['data'][0]['title'],'流程审批中')
        self.assertEqual(inbox('boss')['data'][0]['title'],'待我审批')
        self.assertEqual(inbox('inbound')['data'][0]['title'],'私信')
        self.assertEqual(inbox('boss',page=2,limit=1)['data'],[])
    def test_new_status_unread_and_read_isolation(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO personal_message_reads VALUES ('sales','instance:1:审批中')"))
        self.assertEqual(inbox('sales',unread=True)['total'],0)
        self.assertEqual(inbox('boss')['unread_count'],1)
        with self.engine.begin() as c:
            c.execute(text("UPDATE workflow_instances SET status='已完成'"))
        self.assertEqual(inbox('sales')['unread_count'],1)
        self.assertEqual(inbox('boss')['total'],0)

if __name__=='__main__': unittest.main()
