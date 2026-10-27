import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from api.routes.inventory import get_production_queue_summary


class QueueSummaryTests(unittest.TestCase):
    def test_only_confirmed_unassigned_units_and_binding_subset(self):
        engine = create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE batches (batch_id TEXT, status TEXT)'))
            conn.execute(text('CREATE TABLE units (unit_id TEXT, batch_id TEXT, model_type TEXT, status TEXT, production_line_id TEXT, contract_no TEXT, sales_id TEXT)'))
            conn.execute(text("INSERT INTO batches VALUES ('b1','Confirmed'),('b2','Confirmed'),('empty','Confirmed'),('draft','Predicted'),('active','In_Production')"))
            cases = [
                ('1', 'b1', 'A', 'Pending', None, None, None),
                ('2', 'b1', 'A', 'Confirmed', '', 'contract', 'order'),
                ('3', 'b1', 'B', 'Pending', None, '', 'order'),
                ('4', 'b2', 'A', 'Pending', ' ', ' ', ' '),
                ('5', 'b2', 'A(加高)', 'Pending', None, 'contract', ''),
                ('6', 'b1', 'A', 'In_Production', 'line', None, None),
                ('7', 'b1', 'A', 'Pending', 'line', None, None),
                ('8', 'b1', 'A', 'Completed', None, None, None),
                ('9', 'draft', 'A', 'Pending', None, 'contract', None),
                ('10', 'active', 'A', 'Pending', None, None, None),
            ]
            for row in cases:
                conn.exec_driver_sql('INSERT INTO units VALUES (?,?,?,?,?,?,?)', row)
        with patch('api.routes.inventory.get_engine', return_value=engine), \
             patch('api.routes.inventory.get_enabled_model_names', return_value=['A', 'B']):
            result = get_production_queue_summary()
        self.assertEqual(result['batch_count'], 3)
        rows = {row['model']: row for row in result['data']}
        # 机型严格对齐机型字典：历史数据里的「A(加高)」合并到机型 A，不再单独占一行
        self.assertEqual(rows['A'], dict(model='A', pending=4, ordered=2, batch_ids=['b1', 'b2']))
        self.assertEqual(rows['B']['ordered'], 1)
        self.assertNotIn('A(加高)', rows)
        self.assertEqual(sum(row['pending'] for row in rows.values()), 5)
        engine.dispose()

    def test_empty_queue(self):
        from unittest.mock import MagicMock
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all.return_value = []
        with patch('api.routes.inventory.get_engine', return_value=engine), \
             patch('api.routes.inventory.get_enabled_model_names', return_value=['A']):
            self.assertEqual(get_production_queue_summary(), {'batch_count': 0, 'data': []})
