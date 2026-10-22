import unittest
from io import BytesIO
from zipfile import ZipFile
from contract_bridge.planning_document import render_planning_contract
from contract_bridge.renderer import TEMPLATE


class PlanningDocumentTests(unittest.TestCase):
    def test_shared_template_preserves_fixed_parts_and_all_products(self):
        data = render_planning_contract('HT-123', [
            {'客户名': '测试买方', '机型': 'MODEL-A', '排产数量': 2, '要求交期': '款到30天'},
            {'机型': 'MODEL-B', '排产数量': 3},
        ])
        with ZipFile(BytesIO(data)) as generated, ZipFile(TEMPLATE) as source:
            for name in source.namelist():
                if name != 'word/document.xml':
                    self.assertEqual(source.read(name), generated.read(name))
            xml = generated.read('word/document.xml').decode()
            for value in ['HT-123', '测试买方', 'MODEL-A', 'MODEL-B', '款到30天', '保修一年']:
                self.assertIn(value, xml)
            self.assertFalse(any(n.startswith('word/media/') for n in generated.namelist()))

    def test_extra_products_cannot_be_silently_dropped(self):
        with self.assertRaises(ValueError):
            render_planning_contract('HT-123', [{}] * 5)
