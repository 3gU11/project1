import hashlib
import base64
import json
import unittest
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile
from xml.dom import minidom
import httpx

from contract_bridge import client as bridge
from contract_bridge.renderer import render, TEMPLATE, NS
from contract_bridge.worker import sync_once


def example():
    fields = {'supplier_name': '测试供方', 'contract_no': 'TEST-2026-001', 'buyer_name': '测试购货单位', 'signing_place': '昆山', 'signed_date': '2026年10月20日', 'delivery_date': '款到三十日内', 'settlement_terms': '预付30%，发货前付清尾款', 'total_upper': '贰拾万元整', 'contact_name': '测试联系人', 'contact_phone': '13800000000', 'buyer_address': '测试地址', 'special_requirements': '测试特殊要求', 'remark': '测试用途'}
    for i in range(1, 5):
        fields.update({f'item{i}_product': '测试设备', f'item{i}_brand': '瑞钧', f'item{i}_spec': f'TEST-{i}', f'item{i}_qty': '1', f'item{i}_price': '50000.00'})
    return fields


class RendererTests(unittest.TestCase):
    def test_only_variable_document_part_changes_and_fixed_clauses_survive(self):
        output, digest = render(example())
        self.assertEqual(hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(), digest)
        with ZipFile(TEMPLATE) as original, ZipFile(BytesIO(output)) as generated:
            for name in original.namelist():
                if name != 'word/document.xml':
                    self.assertEqual(original.read(name), generated.read(name), name)
            xml = generated.read('word/document.xml').decode('utf-8')
            for text in ['需方负责安装调试', '保修一年', '测试购货单位', '预付30%', 'TEST-4', '合计人民币金额（大写）']:
                self.assertIn(text, xml)
            doc = minidom.parseString(generated.read('word/document.xml'))
            self.assertEqual(3, len(doc.getElementsByTagNameNS(NS['w'], 'tbl')))
            self.assertEqual(4, xml.count('50000.00'))

    def test_generation_is_deterministic_and_escapes_user_text(self):
        fields = example(); fields['remark'] = '<script>&"'
        first, _ = render(fields)
        self.assertEqual(first, render(fields)[0])
        with ZipFile(BytesIO(first)) as doc:
            self.assertIn('&lt;script&gt;&amp;', doc.read('word/document.xml').decode())


class TransportTests(unittest.TestCase):
    def client(self, handler):
        return httpx.Client(base_url='https://test', transport=httpx.MockTransport(handler))

    def test_contract_queue_uses_spring_route_without_trailing_slash(self):
        seen = []
        def handle(request):
            seen.append(request)
            return httpx.Response(200, json=[])
        with patch.object(bridge, 'client', lambda: self.client(handle)):
            self.assertEqual([], bridge.list_contracts(2, 'submitted'))
        self.assertEqual('/api/ordering/bridge/contracts', seen[0].url.path)
        self.assertEqual({'page': '2', 'state': 'submitted'}, dict(seen[0].url.params))

    def test_prepare_pins_snapshot_hash_and_uploads_preview(self):
        payload = json.dumps(example(), ensure_ascii=False)
        row = {'id': 'revision', 'state': 'submitted', 'payload': payload, 'payloadHash': hashlib.sha256(payload.encode()).hexdigest(), 'templateVersion': 'dealer-contract-v1'}
        uploads = []
        def handle(request):
            if request.method == 'GET': return httpx.Response(200, json=row)
            self.assertLess(len(request.content), 2900000)
            uploads.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={'state': 'preview_ready'})
        with patch.object(bridge, 'client', lambda: self.client(handle)):
            self.assertEqual('preview_ready', bridge.prepare_preview('revision')['state'])
        self.assertTrue(uploads[-1][0].endswith('/preview'))
        self.assertEqual(1, len(uploads))
        content=base64.b64decode(uploads[-1][1]['docxBase64'])
        self.assertEqual(render(example())[0],content)
        self.assertEqual(row['payloadHash'], uploads[-1][1]['payloadHash'])
        self.assertEqual(64, len(uploads[-1][1]['templateHash']))

    def test_interrupted_single_preview_upload_retries_identical_request(self):
        payload=json.dumps(example(),ensure_ascii=False)
        row={'state':'submitted','payload':payload,'payloadHash':hashlib.sha256(payload.encode()).hexdigest(),'templateVersion':'dealer-contract-v1'}
        attempts=[]
        def handle(request):
            if request.method=='GET': return httpx.Response(200,json=row)
            body=json.loads(request.content);attempts.append((request.url.path,body))
            if len(attempts)==1: return httpx.Response(503)
            return httpx.Response(200,json={'state':'preview_ready'})
        with patch.object(bridge,'client',lambda:self.client(handle)):
            with self.assertRaises(RuntimeError): bridge.prepare_preview('revision')
            self.assertEqual(1, len(attempts))
            self.assertTrue(attempts[0][0].endswith('/preview'))
            bridge.prepare_preview('revision')
        self.assertEqual(2, len(attempts))
        self.assertEqual(attempts[0], attempts[1])

    def test_corrupt_snapshot_never_uploads(self):
        row = {'state': 'submitted', 'payload': '{}', 'payloadHash': 'wrong', 'templateVersion': 'dealer-contract-v1'}
        with patch.object(bridge, 'client', lambda: self.client(lambda request: httpx.Response(200, json=row))):
            with self.assertRaises(ValueError): bridge.prepare_preview('revision')

    def test_preview_bytes_must_match_selected_review_revision(self):
        with patch.object(bridge, 'client', lambda: self.client(lambda request: httpx.Response(200, content=b'preview'))):
            self.assertEqual(b'preview', bridge.preview_file('revision', hashlib.sha256(b'preview').hexdigest()))
            with self.assertRaises(ValueError): bridge.preview_file('revision', 'a'*64)

    def test_network_failure_leaves_durable_cloud_queue_and_retries_next_run(self):
        with patch('contract_bridge.worker.list_contracts', return_value=[{'id': 'a'}, {'id': 'b'}]), patch('contract_bridge.worker.prepare_preview', side_effect=[RuntimeError('offline'), {}, {}, {}]) as prepare:
            self.assertEqual({'prepared': 1, 'failed': 1}, sync_once())
            self.assertEqual({'prepared': 2, 'failed': 0}, sync_once())
            self.assertEqual(4, prepare.call_count)

    def test_disabled_and_insecure_configuration_rejected(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(RuntimeError): bridge.client()
        with patch.dict('os.environ', {'CONTRACT_INTEGRATION_ENABLED': 'true', 'CONTRACT_CLOUD_URL': 'http://remote.example', 'CONTRACT_BRIDGE_KEY': 'x'*48}, clear=True):
            with self.assertRaises(RuntimeError): bridge.client()


if __name__ == '__main__':
    unittest.main()
