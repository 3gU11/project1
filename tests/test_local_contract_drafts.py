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
        # 订单没有采集的商业条款留空，等审批人补，不能编造
        self.assertEqual('', fields['settlement_terms'])
        # 供方、税票、办事处信息已改由模板固定或不再打印，字段集里不存在
        for removed in ('supplier_name', 'office_name', 'office_branch', 'office_contact',
                        'office_phone', 'item1_tax'):
            self.assertNotIn(removed, fields)
        # 产品名称也只跟订单走，订单没给就留空
        self.assertEqual('', fields['item2_product'])
        self.assertEqual('', fields['item2_spec'])

    def test_buyer_falls_back_to_local_order_regional_manager_when_snapshot_misses_it(self):
        """云端快照缺大区经理时，用本地已同步订单行的 regional_manager_name 兜底。"""
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS dealer_orders("
                "order_no TEXT, line_no INTEGER, regional_manager_name TEXT)"
            ))
            conn.execute(
                text("INSERT INTO dealer_orders VALUES(:order_no, 1, :manager)"),
                {"order_no": "ORD-RM5", "manager": "朱孝一"},
            )

        row = drafts.create_from_order({
            'orderNo': 'ORD-RM5', 'dealerName': '经销商公司甲',
            'customerName': '客户甲', 'items': [{'productCode': 'A-1', 'quantity': 1}],
        })
        self.assertEqual('朱孝一', row['fields']['dealer_name'])

    def test_order_form_buyer_is_the_regional_manager_not_the_dealer_company(self):
        """自动生成的订货单附件上「需方」取大区经理名字；没有大区经理时才退回经销商名。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-RM1', 'dealerName': '经销商公司甲', 'regionalManagerName': '朱孝一',
            'customerName': '客户甲', 'items': [{'productCode': 'A-1', 'quantity': 1}],
        })
        self.assertEqual('朱孝一', fields['dealer_name'])

        fallback = drafts.map_order_to_contract({
            'orderNo': 'ORD-RM2', 'dealerName': '经销商公司甲',
            'customerName': '客户甲', 'items': [{'productCode': 'A-1', 'quantity': 1}],
        })
        self.assertEqual('经销商公司甲', fallback['dealer_name'])

    def test_existing_pending_draft_uses_regional_manager_as_buyer(self):
        """改动前生成的待审草稿，读取时把「需方」从经销商名刷新成大区经理名。"""
        row = drafts.create_from_order({
            'orderNo': 'ORD-RM3', 'dealerName': '经销商公司甲', 'regionalManagerName': '朱孝一',
            'customerName': '客户甲', 'items': [{'productCode': 'A-1', 'quantity': 1}],
        })
        stored = dict(row['fields'], dealer_name='经销商公司甲')
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f WHERE id=:id"),
                         {'f': json.dumps(stored, ensure_ascii=False), 'id': row['id']})

        healed = drafts.get(row['id'])
        self.assertEqual('朱孝一', healed['fields']['dealer_name'])

    def test_manual_buyer_edit_is_not_overwritten_by_regional_manager_rule(self):
        row = drafts.create_from_order({
            'orderNo': 'ORD-RM4', 'dealerName': '经销商公司甲', 'regionalManagerName': '朱孝一',
            'customerName': '客户甲', 'items': [{'productCode': 'A-1', 'quantity': 1}],
        })
        drafts.update(row['id'], dict(row['fields'], dealer_name='审批人手工填的需方'))
        healed = drafts.get(row['id'])
        self.assertEqual('审批人手工填的需方', healed['fields']['dealer_name'])

    def test_delivery_and_settlement_follow_cloud_form_labels(self):
        """云端表单的「期望交期」「结算方式及期限」要能带出到对应栏位。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-T1', 'customerName': '客户甲',
            'expectedDeliveryDate': '2026 年 11 月（具体等客户通知）',
            'settlementTerms': '预付定金肆万元，安装调试合格付清',
        })
        self.assertEqual('2026 年 11 月（具体等客户通知）', fields['delivery_date'])
        self.assertEqual('预付定金肆万元，安装调试合格付清', fields['settlement_terms'])
        # 云端用中文字段名传值同样认
        cn = drafts.map_order_to_contract({
            'orderNo': 'ORD-T2', '客户名称': '客户甲',
            '期望交期': '2026-11', '结算方式及期限': '月结 30 天',
        })
        self.assertEqual('2026-11', cn['delivery_date'])
        self.assertEqual('月结 30 天', cn['settlement_terms'])

    def test_buyer_address_accepts_split_customer_address(self):
        """云端把「客户信息/地址」拆成客户 + 地址后，名称与地址各归各的栏位。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-A1', 'customerName': '宁波舒勒精密机械有限公司',
            'customerAddress': '余姚模具城', 'contactName': '吴元国',
            'contactPhone': '13905844257',
        })
        self.assertEqual('宁波舒勒精密机械有限公司', fields['buyer_name'])
        self.assertEqual('余姚模具城', fields['buyer_address'])

    def test_office_and_tax_fields_are_not_mapped_any_more(self):
        """办事处信息不再进合同；税票改由单价列表达。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-O1', 'customerName': '客户甲',
            'officeName': '浙江办', 'officeBranch': '余姚办',
            'officeContact': '俞文涛', 'officePhone': '13003767856',
            'items': [{'productCode': 'A-1', 'quantity': 1, 'taxIncluded': '不含税'}],
        })
        for key in ('office_name', 'office_branch', 'office_contact', 'office_phone', 'item1_tax'):
            self.assertNotIn(key, fields)
        self.assertFalse({'office_name', 'office_branch', 'office_contact', 'office_phone'}
                         & set(drafts.missing_required(fields)))
        # 云端明确传「不含税」时，单价列跟着显示不含税
        self.assertEqual('不含税', fields['item1_price'])

    def test_unit_price_defaults_to_tax_included_when_row_has_model(self):
        """单价列：只要该行有规格型号就默认「含税」，没机型的行留空。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-PRICE', 'customerName': '客户甲',
            'items': [
                {'productCode': 'FR-400G', 'quantity': 1},
                {'productCode': 'FR-500XS', 'quantity': 2, 'taxIncluded': True},
                {'productCode': 'FR-7055XS', 'quantity': 1, 'priceNote': '底价'},
                {'productName': '随机配件', 'quantity': 1},
            ],
        })
        self.assertEqual('含税', fields['item1_price'])
        self.assertEqual('含税', fields['item2_price'])
        self.assertEqual('底价', fields['item3_price'])
        self.assertEqual('', fields['item4_price'])
        # 产品名称默认值与纸质合同一致
        self.assertEqual('线切割机床', fields['item1_product'])
        self.assertEqual(drafts.DEFAULT_PRODUCT, '线切割机床')

    def test_obsolete_fields_are_dropped_and_preview_is_invalidated(self):
        """旧草稿里的办事处/税票/供方等废弃键读取时丢弃，旧预览随之作废。"""
        row = drafts.create_from_order({
            'orderNo': 'ORD-O5', 'customerName': '客户甲', 'dealerName': '经销商甲',
            'signedDate': '2026-10-24', 'regionalManagerName': '朱宸',
            'items': [{'model': 'FH-300C', 'quantity': 1}],
        })
        legacy = dict(row['fields'], office_name='浙江办', office_branch='余姚办',
                      office_contact='朱宸', office_phone='13003767856',
                      supplier_name='苏州瑞钧智能科技有限公司', item1_tax='含税',
                      item1_price='50000', item1_brand='瑞钧', contract_no='HT-1')
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f, state='preview_ready', "
                              "preview_hash=:hash WHERE id=:id"),
                         {'f': json.dumps(legacy, ensure_ascii=False), 'hash': 'b' * 64, 'id': row['id']})

        healed = drafts.get(row['id'])
        for key in ('office_name', 'office_branch', 'office_contact', 'office_phone',
                    'supplier_name', 'item1_tax', 'item1_brand', 'contract_no'):
            self.assertNotIn(key, healed['fields'])
        # 旧版金额列不会污染新的单价说明，单价按机型默认「含税」
        self.assertEqual('含税', healed['fields']['item1_price'])
        self.assertNotEqual('50000', healed['fields']['item1_price'])
        # 字段口径变了，旧预览不能继续拿去审批
        self.assertEqual('submitted', healed['state'])
        self.assertIsNone(healed['preview_hash'])

    def test_old_draft_without_price_field_gets_tax_note_backfilled(self):
        """单价列是后加的：改造前生成的草稿没有 item*_price，读取时要补「含税」并刷新默认产品名。"""
        row = drafts.create_from_order({
            'orderNo': 'ORD-OLDPRICE', 'customerName': '客户甲', 'dealerName': '经销商甲',
            'signedDate': '2026-10-26',
            'items': [{'model': 'FR-400XS(PRO)', 'quantity': 1}],
        })
        old_fields = {k: v for k, v in row['fields'].items() if not k.endswith('_price')}
        old_fields['item1_product'] = '瑞钧中走丝线切割'
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f, state='preview_ready', "
                              "preview_hash=:hash WHERE id=:id"),
                         {'f': json.dumps(old_fields, ensure_ascii=False), 'hash': 'c' * 64, 'id': row['id']})

        healed = drafts.get(row['id'])
        # 有机型的行补上默认「含税」，旧默认产品名刷新成「线切割机床」
        self.assertEqual('含税', healed['fields']['item1_price'])
        self.assertEqual('线切割机床', healed['fields']['item1_product'])
        self.assertEqual('', healed['fields']['item2_price'])
        # 字段变化后旧预览作废，需要重新生成
        self.assertEqual('submitted', healed['state'])
        self.assertIsNone(healed['preview_hash'])

    def test_signed_date_is_formatted_like_paper_form(self):
        """签订时间按纸质单写成中文日期；已是中文日期或自由文本则原样保留。"""
        iso = drafts.map_order_to_contract({
            'orderNo': 'ORD-D1', 'dealerName': '经销商甲', 'customerName': '客户甲',
            'createdAt': '2026-10-24 14:22:34',
        })
        self.assertEqual('2026 年 10 月 24 日', iso['signed_date'])
        self.assertEqual(
            '2026 年 10 月 23 日',
            drafts.map_order_to_contract({'orderNo': 'ORD-D2', 'signedDate': '2026 年 10 月 23 日'})['signed_date'],
        )
        self.assertEqual(
            '待定',
            drafts.map_order_to_contract({'orderNo': 'ORD-D3', 'signedDate': '待定'})['signed_date'],
        )

    def test_paper_sample_renders_expected_values(self):
        """用 2026-10-23 纸质样单的数据端到端渲染，逐项核对栏位取值。"""
        from contract_bridge.renderer import render_order_form

        order = {
            'orderNo': 'ORD-PAPER', 'dealerName': '陈利春', 'officeName': '浙江办',
            'signedDate': '2026-10-23',
            'items': [
                {'productName': '瑞钧中走丝线切割', 'productCode': 'FR-500XS(PRO)', 'quantity': 3},
                {'productName': '瑞钧中走丝线切割', 'productCode': 'FR-7055XS(PRO)', 'quantity': 1},
            ],
            'remark': '标配',
            'expectedDeliveryDate': '2026 年 11 月（具体等客户通知）',
            'settlementTerms': '预付定金肆万元，安装调试合格付清',
            'customerName': '宁波舒勒精密机械有限公司', 'customerAddress': '余姚模具城',
            'contactName': '吴元国', 'contactPhone': '13905844257',
            'officeBranch': '余姚办', 'officeContact': '俞文涛', 'officePhone': '13003767856',
            'specialRequirements': '收货信息直接写办事处信息',
        }
        blob, _ = render_order_form(drafts.map_order_to_contract(order))
        text = document_text(blob)
        self.assertNotIn('{{', text)
        # 纸质合同固定内容（红框值）直接印在成品上
        for expected in (
            '瑞钧机械办事处订货合同', '昆山瑞钧机械科技有限公司',
            '（底价）', '含税', '需方负责安装调试、培训及售后服务',
            '机械精度、电气部分保修一年',
            '中国工商银行昆山北门分理处', '1102 2320 0900 0027 757',
            '0512-57175508', '0512-57175608',
        ):
            self.assertIn(expected, text)
        # 可变栏位按订单快照填充
        for expected in (
            '陈利春', '2026 年 10 月 23 日',
            'FR-500XS(PRO)', 'FR-7055XS(PRO)', '标配',
            '2026 年 11 月（具体等客户通知）', '预付定金肆万元，安装调试合格付清',
            '宁波舒勒精密机械有限公司', '余姚模具城', '吴元国', '13905844257',
            '收货信息直接写办事处信息',
        ):
            self.assertIn(expected, text)
        # 办事处信息不再印到合同上
        for removed in ('浙江办', '余姚办', '俞文涛', '13003767856', '苏州瑞钧智能科技有限公司'):
            self.assertNotIn(removed, text)

    def test_same_model_batch_lines_are_merged_with_summed_quantity(self):
        """云端按批次行下发同型号时，订货单合并成一行、数量相加。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-M1', 'customerName': '客户甲',
            'items': [
                {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'finished'},
                {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'wip'},
                {'model': 'FR-400XS(PRO)', 'quantity': '2', 'inventoryType': 'finished'},
            ],
        })
        self.assertEqual('FH-300C', fields['item1_spec'])
        self.assertEqual('2', fields['item1_qty'])
        self.assertEqual('FR-400XS(PRO)', fields['item2_spec'])
        self.assertEqual('2', fields['item2_qty'])
        self.assertEqual('', fields['item3_spec'])

    def test_heightened_items_are_split_from_normal_and_marked_in_spec(self):
        """加高机型在规格型号后标「（加高）」，与同型号普通机分两行。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-M2', 'customerName': '客户甲',
            'items': [
                {'model': 'FR-400XS(PRO)', 'quantity': 1, 'inventoryType': 'finished'},
                {'model': 'FR-400XS(PRO)', 'quantity': 1, 'inventoryType': 'heightened'},
                {'model': 'FR-400XS(PRO)（加高）', 'quantity': 1, 'inventoryType': 'wip'},
            ],
        })
        self.assertEqual('FR-400XS(PRO)', fields['item1_spec'])
        self.assertEqual('1', fields['item1_qty'])
        self.assertEqual('FR-400XS(PRO)（加高）', fields['item2_spec'])
        self.assertEqual('2', fields['item2_qty'])
        self.assertEqual('', fields['item3_spec'])

    def test_real_order_batch_lines_render_as_merged_rows(self):
        """真实订单 8 条批次行应渲染成 4 行明细，加高机单独一行并带标记。"""
        from contract_bridge.renderer import render_order_form

        items = [
            {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'finished'},
            {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'wip'},
            {'model': 'FR-400G', 'quantity': '1.000', 'inventoryType': 'finished'},
            {'model': 'FR-400G', 'quantity': '1.000', 'inventoryType': 'wip'},
            {'model': 'FR-400XS(PRO)', 'quantity': '1.000', 'inventoryType': 'finished'},
            {'model': 'FR-400XS(PRO)', 'quantity': '1.000', 'inventoryType': 'wip'},
            {'model': 'FR-400XS(PRO)', 'quantity': '1.000', 'inventoryType': 'heightened'},
            {'model': 'FR-400XS(PRO)', 'quantity': '1.000', 'inventoryType': 'heightened'},
        ]
        blob, _ = render_order_form(drafts.map_order_to_contract(
            {'orderNo': 'ORD-M3', 'customerName': '客户甲', 'items': items}))
        text = document_text(blob)
        self.assertNotIn('{{', text)
        self.assertIn('FR-400XS(PRO)（加高）', text)
        self.assertEqual(4, text.count(drafts.DEFAULT_PRODUCT))
        # 表头的「（底价）」固定印一次；单价列每行有机型就默认「含税」
        self.assertEqual(1, text.count('（底价）'))
        self.assertEqual(4, text.count('含税'))

    def test_stale_preview_is_regenerated_after_mapping_upgrade(self):
        """映射规则升级后旧预览要作废，重新生成时按合并/加高规则渲染。"""
        items = [
            {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'finished'},
            {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'wip'},
            {'model': 'FR-400XS(PRO)', 'quantity': '1.000', 'inventoryType': 'finished'},
            {'model': 'FR-400XS(PRO)', 'quantity': '1.000', 'inventoryType': 'heightened'},
        ]
        row = drafts.create_from_order({'orderNo': 'ORD-M4', 'dealerName': '经销商甲',
                                        'customerName': '客户甲', 'items': items})
        # 模拟改动前生成的草稿：按批次行逐行存 4 行
        legacy = dict(row['fields'])
        old_rows = [('FH-300C', '1'), ('FH-300C', '1'), ('FR-400XS(PRO)', '1'), ('FR-400XS(PRO)', '1')]
        for index in range(1, 5):
            spec, qty = old_rows[index - 1]
            legacy.update({
                f'item{index}_product': '瑞钧中走丝线切割', f'item{index}_spec': spec,
                f'item{index}_qty': qty, f'item{index}_tax': '',
            })
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f, state='preview_ready', "
                              "preview_hash=:hash WHERE id=:id"),
                         {'f': json.dumps(legacy, ensure_ascii=False), 'hash': 'a' * 64, 'id': row['id']})

        refreshed = drafts.get(row['id'])
        self.assertEqual('submitted', refreshed['state'])
        self.assertIsNone(refreshed['preview_hash'])
        self.assertEqual('FH-300C', refreshed['fields']['item1_spec'])
        self.assertEqual('2', refreshed['fields']['item1_qty'])
        self.assertEqual('FR-400XS(PRO)', refreshed['fields']['item2_spec'])
        self.assertEqual('1', refreshed['fields']['item2_qty'])
        self.assertEqual('FR-400XS(PRO)（加高）', refreshed['fields']['item3_spec'])
        self.assertEqual('1', refreshed['fields']['item3_qty'])
        self.assertEqual('', refreshed['fields']['item4_spec'])

        prepared = drafts.prepare(row['id'])
        self.assertEqual('preview_ready', prepared['state'])
        # prepare 已把规整后的字段落库，之后不会再判为过期
        self.assertEqual('preview_ready', drafts.get(row['id'])['state'])

    def test_manual_item_quantity_edit_is_not_overwritten(self):
        """审批人改过明细数量时，不按快照重排明细行。"""
        items = [
            {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'finished'},
            {'model': 'FH-300C', 'quantity': '1.000', 'inventoryType': 'finished'},
        ]
        row = drafts.create_from_order({'orderNo': 'ORD-M5', 'dealerName': '经销商甲',
                                        'customerName': '客户甲', 'items': items})
        edited = dict(row['fields'])
        edited.update({
            'item1_product': '瑞钧中走丝线切割', 'item1_spec': 'FH-300C', 'item1_qty': '5',
            'item2_product': '瑞钧中走丝线切割', 'item2_spec': 'FH-300C', 'item2_qty': '1',
        })
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f WHERE id=:id"),
                         {'f': json.dumps(edited, ensure_ascii=False), 'id': row['id']})

        kept = drafts.get(row['id'])['fields']
        self.assertEqual('5', kept['item1_qty'])
        self.assertEqual('FH-300C', kept['item2_spec'])

    def test_merged_rows_keep_blank_quantity_when_missing(self):
        """同型号两行都没有数量时保持空白，不把缺失数量当 0 相加。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-M6', 'customerName': '客户甲',
            'items': [{'model': 'FH-300C'}, {'model': 'FH-300C'}],
        })
        self.assertEqual('FH-300C', fields['item1_spec'])
        self.assertEqual('', fields['item1_qty'])

    def test_rows_without_spec_are_not_merged(self):
        """没有规格型号的行不参与合并，避免把不同设备并成一行。"""
        fields = drafts.map_order_to_contract({
            'orderNo': 'ORD-M7', 'customerName': '客户甲',
            'items': [
                {'productName': '设备A', 'quantity': 1},
                {'productName': '设备B', 'quantity': 2},
            ],
        })
        self.assertEqual('设备A', fields['item1_product'])
        self.assertEqual('设备B', fields['item2_product'])
        self.assertEqual('1', fields['item1_qty'])
        self.assertEqual('2', fields['item2_qty'])

    def test_approved_draft_keeps_state_and_preview(self):
        """已归档草稿不因映射规则升级被作废，历史字段与附件保持原样。"""
        row = drafts.create_from_order({
            'orderNo': 'ORD-M8', 'dealerName': '经销商甲', 'customerName': '客户甲',
            'signedDate': '2026-10-24',
            'items': [{'model': 'FH-300C', 'quantity': 1}, {'model': 'FH-300C', 'quantity': 1}],
        })
        approved = drafts.prepare(row['id'])
        drafts.review(approved['id'], approved['preview_hash'], 'approved', 'boss', '核对无误')
        # 模拟老口径字段（含已废弃键）：已归档草稿不做规整，展示口径与归档时一致
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f WHERE id=:id"),
                         {'f': json.dumps(dict(row['fields'], item1_tax=''), ensure_ascii=False),
                          'id': row['id']})

        kept = drafts.get(row['id'])
        self.assertEqual('approved', kept['state'])
        self.assertTrue(kept['preview_hash'])
        self.assertEqual('', kept['fields']['item1_tax'])

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
        """订货合同模板里的 {{占位符}} 必须全部替换掉，不能漏到成品里。"""
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
        for expected in ('昆山瑞钧机械科技有限公司', '陈利春', '宁波舒勒精密机械有限公司',
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
            'item1_qty': '5.000', 'item1_price': '50000',
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
        self.assertEqual('陈利春', fields['dealer_name'])
        self.assertEqual('青岛铭青', fields['buyer_name'])
        self.assertEqual('FR-400XS(PRO)', fields['item1_spec'])
        # 旧版的金额列 item1_price=50000 不能当成新合同的单价说明；单价按行默认「含税」
        self.assertEqual('含税', fields['item1_price'])
        # 旧键与废弃键清掉，编辑弹窗不再出现无效项
        for removed in ('supplier_name', 'contract_no', 'item1_brand',
                        'office_branch', 'item1_tax'):
            self.assertNotIn(removed, fields)
        self.assertNotEqual('50000', fields['item1_price'])
        # 旧值里的 5.000 也顺手规整成 5
        self.assertEqual('5', fields['item1_qty'])
        # 缺失清单按新字段集算，需方不再算缺失
        self.assertNotIn('dealer_name', healed['missing_fields'])
        self.assertIn('signed_date', healed['missing_fields'])

    def test_existing_drafts_get_signed_date_normalized(self):
        """改动前生成的草稿：签订时间转中文日期，旧预览作废等待重新生成。"""
        row = drafts.create_from_order({
            'orderNo': 'ORD-BF', 'dealerName': '经销商甲', 'customerName': '客户甲',
            'createdAt': '2026-10-24 14:22:34',
            'items': [{'productCode': 'A-1', 'quantity': 1}],
        })
        stored = dict(row['fields'], signed_date='2026-10-24 14:22:34')
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:f WHERE id=:id"),
                         {'f': json.dumps(stored, ensure_ascii=False), 'id': row['id']})

        healed = drafts.get(row['id'])
        self.assertEqual('2026 年 10 月 24 日', healed['fields']['signed_date'])
        self.assertEqual('submitted', healed['state'])

    def test_current_field_set_is_not_touched(self):
        """新字段集的草稿不能被"升级"逻辑改写，审批人改过的值要保留。"""
        row = drafts.create_from_order({'orderNo': 'ORD-8', 'dealerName': '原值', 'customerName': '客户甲'})
        updated = drafts.update(row['id'], dict(row['fields'], dealer_name='人工改过'))
        healed = drafts.get(row['id'])
        self.assertEqual('人工改过', healed['fields']['dealer_name'])
        self.assertEqual(updated['fields']['buyer_name'], healed['fields']['buyer_name'])
        self.assertEqual(updated['fields']['item1_qty'], healed['fields']['item1_qty'])

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
            '结算方式': '月结 30 天', '交货时间': '2026 年 11 月',
            'items': [{'规格型号': 'FR-400XS(PRO)', '数量': 5}],
        })
        self.assertEqual('陈利春', fields['dealer_name'])
        self.assertEqual('青岛铭青', fields['buyer_name'])
        self.assertEqual('月结 30 天', fields['settlement_terms'])
        self.assertEqual('2026 年 11 月', fields['delivery_date'])
        self.assertEqual('FR-400XS(PRO)', fields['item1_spec'])
        self.assertEqual('5', fields['item1_qty'])
        # 办事处信息已经不在合同字段集里，中文别名也不会再带出
        self.assertNotIn('office_name', fields)

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

    def test_reject_for_order_rejects_unarchived_drafts_only(self):
        """订单驳回时，只连带驳回未归档的草稿；已归档的审批记录保持不动。"""
        base = {
            'orderNo': 'ORD-R1', 'customerName': '客户甲', 'dealerName': '经销商甲',
            'signedDate': '2026-10-24',
        }
        pending = drafts.prepare(drafts.create_from_order(base)['id'])
        archived = drafts.prepare(drafts.create_from_order({**base, 'remark': '第二版'})['id'])
        drafts.review(archived['id'], archived['preview_hash'], 'approved', 'boss', '核对无误')

        self.assertEqual(1, drafts.reject_for_order('ORD-R1', 'boss', '库存不足'))
        rejected = drafts.get(pending['id'])
        self.assertEqual('rejected', rejected['state'])
        self.assertEqual('库存不足', rejected['review_note'])
        self.assertEqual('boss', rejected['reviewer'])
        self.assertEqual('approved', drafts.get(archived['id'])['state'])

        # 已经全部处理过的订单、空订单号都不应报错
        self.assertEqual(0, drafts.reject_for_order('ORD-R1', 'boss', '再次驳回'))
        self.assertEqual(0, drafts.reject_for_order('', 'boss'))

    def test_list_latest_states_reports_newest_version_and_review_audit(self):
        base = {
            'orderNo': 'ORD-L1', 'customerName': '客户甲', 'dealerName': '经销商甲',
            'signedDate': '2026-10-24',
        }
        drafts.prepare(drafts.create_from_order(base)['id'])
        latest = drafts.prepare(drafts.create_from_order({**base, 'remark': '第二版'})['id'])
        drafts.review(latest['id'], latest['preview_hash'], 'approved', 'boss', '核对无误')

        states = drafts.list_latest_states(['ORD-L1', 'ORD-NONE', ''])
        self.assertEqual('approved', states['ORD-L1']['state'])
        self.assertEqual('boss', states['ORD-L1']['reviewer'])
        self.assertTrue(states['ORD-L1']['reviewed_at'])
        self.assertNotIn('ORD-NONE', states)
        self.assertEqual({}, drafts.list_latest_states([]))

    def test_resubmit_clears_previous_review_audit(self):
        base = {
            'orderNo': 'ORD-RS', 'customerName': '客户甲', 'dealerName': '经销商甲',
            'signedDate': '2026-10-24',
        }
        draft = drafts.prepare(drafts.create_from_order(base)['id'])
        drafts.review(draft['id'], draft['preview_hash'], 'rejected', 'boss', '信息不全')

        resubmitted = drafts.update(draft['id'], draft['fields'])
        self.assertEqual('submitted', resubmitted['state'])
        self.assertFalse(resubmitted['reviewer'])
        self.assertFalse(resubmitted['review_note'])
        self.assertFalse(resubmitted['reviewed_at'])

    def test_latest_document_returns_docx_for_contract_conversion(self):
        """转合同时要能拿到系统生成的订货单文件。"""
        base = {
            'orderNo': 'ORD-DOC1', 'customerName': '客户甲', 'dealerName': '经销商甲',
            'signedDate': '2026-10-24',
        }
        created = drafts.create_from_order(base)

        # 附件名前缀用云端回传的客户名称，不再用订单号
        content, file_name = drafts.latest_document('ORD-DOC1', '客户甲')
        self.assertTrue(content.startswith(b'PK'))
        self.assertEqual('客户甲-订货单.docx', file_name)

        # 没有客户名称时退回订单号，保证历史订单仍可归档
        _, fallback_name = drafts.latest_document('ORD-DOC1')
        self.assertEqual('ORD-DOC1-订货单.docx', fallback_name)
        _, blank_name = drafts.latest_document('ORD-DOC1', '   ')
        self.assertEqual('ORD-DOC1-订货单.docx', blank_name)

        # 客户名称里的文件夹/通配符等非法字符要剔除，不能带进落盘路径
        _, cleaned_name = drafts.latest_document('ORD-DOC1', ' 甲/乙*丙:丁 ')
        self.assertEqual('甲乙丙丁-订货单.docx', cleaned_name)

        # 生成过预览后优先复用预览内容，不再重复渲染
        prepared = drafts.prepare(created['id'])
        preview_content, _ = drafts.latest_document('ORD-DOC1', '客户甲')
        self.assertTrue(preview_content.startswith(b'PK'))
        self.assertEqual(64, len(prepared['preview_hash']))

        self.assertIsNone(drafts.latest_document('ORD-NONE'))
        self.assertIsNone(drafts.latest_document(''))

    def test_order_form_file_name_uses_customer_name_prefix(self):
        """订货单附件文件名：客户名称优先，非法字符剔除，空值退回订单号。"""
        self.assertEqual('广东-订货单.docx', drafts.order_form_file_name('DO-9', '广东'))
        self.assertEqual('ORD-DOC2-订货单.docx', drafts.order_form_file_name('ORD-DOC2', ''))
        self.assertEqual('AB-订货单.docx', drafts.order_form_file_name('ORD-DOC2', 'A?B'))
        self.assertEqual('订货单.docx', drafts.order_form_file_name('', ''))


if __name__ == '__main__':
    unittest.main()
