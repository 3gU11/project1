import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, text
from crud.personal_messages import inbox


class PersonalInboxTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        with self.engine.begin() as c:
            c.connection.driver_connection.create_function(
                'CONCAT', -1, lambda *v: ''.join(str(x or '') for x in v)
            )
            for ddl in [
                'workflow_instances (id integer,instance_no text,workflow_key text,business_type text,'
                'business_id text,status text,initiator_id text,created_at text,completed_at text)',
                'workflow_tasks (id integer,instance_id integer,status text,assignee_id text,assigned_at text)',
                'workflow_derived_tasks (id integer,instance_id integer,status text,task_type text,'
                'object_id text,task_no text,assignee_id text,created_at text,completed_at text)',
                'workflow_notifications (id integer,title text,content text,recipient_id text,'
                'notification_type text,created_at text)',
                'workflow_models (id integer,workflow_key text,name text,direction text)',
                'personal_message_reads (username text,message_key text)',
            ]:
                c.execute(text('CREATE TABLE ' + ddl))
            c.execute(text("INSERT INTO workflow_models VALUES (1,'shipment-recall','发货撤回','逆向')"))
            c.execute(text("INSERT INTO workflow_instances VALUES "
                           "(1,'WF1','shipment-recall','订单','SO1','审批中','sales','2026-10-19',NULL)"))
            c.execute(text("INSERT INTO workflow_tasks VALUES (1,1,'待处理','boss','2026-10-19')"))
            c.execute(text("INSERT INTO workflow_derived_tasks VALUES "
                           "(1,1,'待处理','重入库','96-01-001','RI-1','inbound','2026-10-19',NULL)"))
            c.execute(text("INSERT INTO workflow_notifications VALUES "
                           "(1,'私信','内容','inbound','流程通知','2026-10-19')"))
        self.mock = patch('crud.personal_messages.get_engine', return_value=self.engine)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.engine.dispose()

    def test_approver_and_worker_get_actionable_messages(self):
        boss = inbox('boss')
        self.assertEqual(boss['total'], 1)
        # 审批人只需要知道"什么流程、哪个对象、要我做审批"
        self.assertEqual(boss['data'][0]['title'], '待审批 · 发货撤回')
        self.assertIn('SO1', boss['data'][0]['content'])
        self.assertIn('等待你审批', boss['data'][0]['content'])

        inbound = inbox('inbound')
        titles = [item['title'] for item in inbound['data']]
        self.assertIn('待重入库 · 发货撤回', titles)
        self.assertIn('私信', titles)
        # 同一次重入库只出现一次：派生任务条目承载，通知表里的同类型被排除
        self.assertEqual(len([t for t in titles if '重入库' in t]), 1)

    def test_initiator_sees_only_key_stages(self):
        # 审批中是过程态，不再推给发起人
        self.assertEqual(inbox('sales')['total'], 0)

        with self.engine.begin() as c:
            c.execute(text("UPDATE workflow_instances SET status='已通过'"))
        approved = inbox('sales')['data'][0]
        self.assertEqual(approved['title'], '审批已通过 · 发货撤回')
        self.assertIn('正在执行', approved['content'])

        # 重入库完成后给出明确的收尾文案
        with self.engine.begin() as c:
            c.execute(text("UPDATE workflow_instances SET status='已完成'"))
        done = inbox('sales')['data'][0]
        self.assertEqual(done['title'], '流程已完成 · 发货撤回')
        self.assertIn('重入库已完成，流程结束', done['content'])

    def test_rejected_and_failed_are_reported(self):
        with self.engine.begin() as c:
            c.execute(text("UPDATE workflow_instances SET status='已拒绝'"))
        rejected = inbox('sales')['data'][0]
        self.assertEqual(rejected['title'], '审批被拒绝 · 发货撤回')

        with self.engine.begin() as c:
            c.execute(text("UPDATE workflow_instances SET status='执行异常'"))
        failed = inbox('sales')['data'][0]
        self.assertEqual(failed['title'], '执行失败 · 发货撤回')
        self.assertIn('联系管理员', failed['content'])

    def test_unread_and_read_isolation(self):
        self.assertEqual(inbox('stranger')['total'], 0)
        self.assertEqual(inbox('boss')['unread_count'], 1)

        with self.engine.begin() as c:
            c.execute(text("INSERT INTO personal_message_reads VALUES ('sales','instance:1:已通过')"))
        self.assertEqual(inbox('sales', unread=True)['total'], 0)

        # 状态推进产生新的 message_key，算作新消息
        with self.engine.begin() as c:
            c.execute(text("UPDATE workflow_instances SET status='已完成'"))
        self.assertEqual(inbox('sales')['unread_count'], 1)
        self.assertEqual(inbox('sales', page=2, limit=1)['data'], [])


if __name__ == '__main__':
    unittest.main()
