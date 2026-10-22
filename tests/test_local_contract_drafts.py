import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from crud import local_contract_drafts as drafts


class LocalContractDraftTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.engine_patch = patch.object(drafts, 'get_engine', return_value=self.engine)
        self.engine_patch.start()
        drafts.ensure_table()

    def tearDown(self):
        self.engine_patch.stop()
        self.engine.dispose()

    def test_maps_order_form_and_keeps_missing_contract_fields_blank(self):
        row = drafts.create_from_order({'orderNo': 'ORD-1', 'customerName': '客户甲', 'contactPhone': '13800000000', 'items': [{'productName': '设备A', 'quantity': 2, 'unitPrice': 100}]})
        self.assertEqual('客户甲', row['fields']['buyer_name'])
        self.assertEqual('设备A', row['fields']['item1_product'])
        self.assertEqual('100', row['fields']['item1_price'])
        self.assertEqual('', row['fields']['supplier_name'])
        self.assertEqual('', row['fields']['settlement_terms'])

    def test_duplicate_source_form_is_idempotent_and_changed_form_creates_new_draft(self):
        order = {'orderNo': 'ORD-2', 'customerName': '客户甲'}
        first = drafts.create_from_order(order)
        again = drafts.create_from_order(order)
        changed = drafts.create_from_order({**order, 'remark': '更新'})
        self.assertEqual(first['id'], again['id'])
        self.assertTrue(first['_created'])
        self.assertFalse(again['_created'])
        self.assertNotEqual(first['id'], changed['id'])

    def test_preview_allows_blanks_and_hash_tracks_preview(self):
        row = drafts.create_from_order({'orderNo': 'ORD-3', 'customerName': '客户甲'})
        blank_preview = drafts.prepare(row['id'])
        self.assertEqual('preview_ready', blank_preview['state'])
        self.assertIn('supplier_name', blank_preview['missing_fields'])
        fields = dict(row['fields'], supplier_name='供方', signing_place='昆山', signed_date='2026-10-22', settlement_terms='面议')
        updated = drafts.update(row['id'], fields)
        preview = drafts.prepare(row['id'])
        self.assertEqual('preview_ready', preview['state'])
        self.assertEqual(64, len(preview['preview_hash']))
        self.assertNotEqual(updated['preview_hash'], preview['preview_hash'])


if __name__ == '__main__':
    unittest.main()
