import re
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from crud import local_contract_drafts as drafts


def document_text(blob: bytes) -> str:
    with zipfile.ZipFile(BytesIO(blob)) as package:
        xml = package.read('word/document.xml').decode('utf-8')
    return ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', xml))


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
        row = drafts.create_from_order({
            'orderNo': 'ORD-1', 'customerName': '客户甲', 'contactPhone': '13800000000',
            'items': [{'productName': '设备A', 'productCode': 'A-1', 'quantity': 2}],
        })
        fields = row['fields']
        self.assertEqual('客户甲', fields['buyer_name'])
        self.assertEqual('13800000000', fields['contact_phone'])
        self.assertEqual('设备A', fields['item1_product'])
        self.assertEqual('A-1', fields['item1_spec'])
        self.assertEqual('2', fields['item1_qty'])
        # 供方是固定值，不依赖订单
        self.assertEqual(drafts.DEFAULT_SUPPLIER, fields['supplier_name'])
        # 订单没有采集的商业条款留空，等审批人补，不能编造
        self.assertEqual('', fields['settlement_terms'])
        self.assertEqual('', fields['item1_tax'])
        self.assertEqual('', fields['office_branch'])
        # 产品名称也只跟订单走，订单没给就留空
        self.assertEqual('', fields['item2_product'])
        self.assertEqual('', fields['item2_spec'])

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
        self.assertIn('dealer_name', blank_preview['missing_fields'])
        self.assertIn('signed_date', blank_preview['missing_fields'])
        fields = dict(row['fields'], dealer_name='经销商甲', signed_date='2026-10-23', settlement_terms='面议')
        updated = drafts.update(row['id'], fields)
        preview = drafts.prepare(row['id'])
        self.assertEqual('preview_ready', preview['state'])
        self.assertEqual(64, len(preview['preview_hash']))
        self.assertNotEqual(updated['preview_hash'], preview['preview_hash'])

    def test_render_fills_every_placeholder(self):
        """订货单模板里的 {{占位符}} 必须全部替换掉，不能漏到成品里。"""
        from contract_bridge.renderer import render_order_form

        order = {
            'orderNo': 'ORD-4', 'dealerName': '陈利春', 'customerName': '宁波舒勒精密机械有限公司',
            'contactName': '吴元国', 'contactPhone': '13905844257', 'deliveryAddress': '余姚模具城',
            'signedDate': '2026 年 10 月 23 日', 'deliveryDate': '2026 年 11 月（具体等客户通知）',
            'settlementTerms': '预付定金肆万元，安装调试合格付清', 'remark': '标配',
            'items': [
                {'productName': '瑞钧中走丝线切割', 'productCode': 'FR-500XS(PRO)', 'quantity': 3},
                {'productName': '瑞钧中走丝线切割', 'productCode': 'FR-7055XS(PRO)', 'quantity': 1},
            ],
        }
        blob, template_hash = render_order_form(drafts.map_order_to_contract(order))
        text = document_text(blob)
        self.assertNotIn('{{', text)
        self.assertEqual(64, len(template_hash))
        for expected in ('苏州瑞钧智能科技有限公司', '陈利春', '宁波舒勒精密机械有限公司',
                         'FR-500XS(PRO)', '余姚模具城', '标配'):
            self.assertIn(expected, text)

    def test_render_leaves_missing_values_blank(self):
        from contract_bridge.renderer import render_order_form

        blob, _ = render_order_form(drafts.map_order_to_contract({'orderNo': 'ORD-5', 'customerName': '客户甲'}))
        text = document_text(blob)
        self.assertNotIn('{{', text)
        self.assertIn('客户甲', text)


if __name__ == '__main__':
    unittest.main()
