import json
import re
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch
from sqlalchemy import create_engine, text
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
        text_content = document_text(blob)
        self.assertNotIn('{{', text_content)
        self.assertIn('客户甲', text_content)

    def test_quantity_drops_trailing_zeros(self):
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-7', 'customerName': '客户甲',
            'items': [{'productName': '设备A', 'quantity': '5.000'}, {'productName': '设备B', 'quantity': 5.5}],
        })
        self.assertEqual('5', fields['item1_qty'])
        self.assertEqual('5.5', fields['item2_qty'])

    def test_legacy_draft_fields_are_upgraded_from_snapshot(self):
        """换模板之前生成的草稿只有旧字段集，读取时要按快照补齐新模板需要的键。"""
        order = {
            'orderNo': 'ORD-6', 'dealerName': '陈利春', 'customerName': '青岛铭青',
            'contactName': '高望', 'contactPhone': '16651615305',
            'items': [{'productCode': 'FR-400XS(PRO)', 'quantity': '5.000'}],
        }
        row = drafts.create_from_order(order)
        legacy = {
            'supplier_name': '', 'contract_no': '', 'buyer_name': '青岛铭青', 'signing_place': '',
            'signed_date': '', 'delivery_date': '', 'settlement_terms': '', 'total_upper': '',
            'buyer_address': '', 'contact_name': '高望', 'contact_phone': '16651615305',
            'special_requirements': '', 'remark': '', 'accessories': '',
            'item1_product': 'FR-400XS(PRO)', 'item1_brand': '', 'item1_spec': 'FR-400XS(PRO)',
            'item1_qty': '5.000', 'item1_price': '',
        }
        for index in range(2, 5):
            for suffix in ('product', 'brand', 'spec', 'qty', 'price'):
                legacy[f'item{index}_{suffix}'] = ''
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f WHERE id=:id"),
                         {'f': json.dumps(legacy, ensure_ascii=False), 'id': row['id']})

        healed = drafts.get(row['id'])
        fields = healed['fields']
        # 旧字段集没有的键被补上
        self.assertEqual(drafts.DEFAULT_SUPPLIER, fields['supplier_name'])
        self.assertEqual('陈利春', fields['dealer_name'])
        self.assertIn('office_branch', fields)
        self.assertIn('item1_tax', fields)
        # 旧键清掉，编辑弹窗不再出现无效项
        self.assertNotIn('contract_no', fields)
        self.assertNotIn('item1_price', fields)
        # 旧值里的 5.000 也顺手规整成 5
        self.assertEqual('5', fields['item1_qty'])
        # 缺失清单按新字段集算，需方不再算缺失
        self.assertNotIn('dealer_name', healed['missing_fields'])
        self.assertIn('signed_date', healed['missing_fields'])

    def test_current_field_set_is_not_touched(self):
        """新字段集的草稿不能被"升级"逻辑改写，审批人改过的值要保留。"""
        row = drafts.create_from_order({'orderNo': 'ORD-8', 'dealerName': '原值', 'customerName': '客户甲'})
        updated = drafts.update(row['id'], dict(row['fields'], dealer_name='人工改过'))
        healed = drafts.get(row['id'])
        self.assertEqual('人工改过', healed['fields']['dealer_name'])
        self.assertEqual(updated['fields']['supplier_name'], healed['fields']['supplier_name'])

    def test_product_name_defaults_only_when_model_present(self):
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-9', 'customerName': '客户甲',
            'items': [{'productCode': 'FR-500XS', 'quantity': 1}, {'quantity': 2}],
        })
        self.assertEqual(drafts.DEFAULT_PRODUCT, fields['item1_product'])
        self.assertEqual('', fields['item2_product'])

    def test_chinese_and_alternative_field_names_are_recognized(self):
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-10', '经销商': '陈利春', '购货单位': '青岛铭青',
            '结算方式': '月结 30 天', '交货时间': '2026 年 11 月', '所属办事处': '浙江办',
            'items': [{'规格型号': 'FR-400XS(PRO)', '数量': 5, '税票': '含税'}],
        })
        self.assertEqual('陈利春', fields['dealer_name'])
        self.assertEqual('青岛铭青', fields['buyer_name'])
        self.assertEqual('月结 30 天', fields['settlement_terms'])
        self.assertEqual('2026 年 11 月', fields['delivery_date'])
        self.assertEqual('浙江办', fields['office_name'])
        self.assertEqual('FR-400XS(PRO)', fields['item1_spec'])
        self.assertEqual('5', fields['item1_qty'])
        self.assertEqual('含税', fields['item1_tax'])

    def test_extra_item_rows_are_added_when_order_has_more_models(self):
        from contract_bridge.renderer import render_order_form

        items = [{'productCode': f'M{i}', 'quantity': i} for i in range(1, 7)]
        blob, _ = render_order_form(drafts.map_order_to_contract(
            {'orderNo': 'ORD-11', 'customerName': '客户甲', 'items': items}))
        content = document_text(blob)
        self.assertNotIn('{{', content)
        for index in range(1, 7):
            self.assertIn(f'M{index}', content)
        # 6 行都补上了产品名称
        self.assertEqual(6, content.count(drafts.DEFAULT_PRODUCT))


if __name__ == '__main__':
    unittest.main()
