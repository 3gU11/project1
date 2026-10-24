"""Cloud is the durable queue. Failed uploads/reviews can safely be retried."""
import base64
import hashlib
import json
import os
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv
from .renderer import render

load_dotenv()
CONTRACTS_PATH = '/api/ordering/bridge/contracts'


def configured():
    return os.getenv('CONTRACT_INTEGRATION_ENABLED', '').lower() == 'true'


def client():
    if not configured():
        raise RuntimeError('合同接入未启用')
    base = os.getenv('CONTRACT_CLOUD_URL', '').rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')):
        raise RuntimeError('合同云端地址必须使用 HTTPS（本机测试除外）')
    secret = os.getenv('CONTRACT_BRIDGE_KEY', '')
    if len(secret) < 32:
        raise RuntimeError('合同桥接密钥未配置或长度不足')
    return httpx.Client(base_url=base, headers={'X-Contract-Bridge-Key': secret}, timeout=60, trust_env=False, follow_redirects=False)


def checked(response):
    if response.is_error:
        # Never log the request headers or contract content.
        raise RuntimeError(f'合同云端请求失败 HTTP {response.status_code}')
    if response.is_redirect:
        raise RuntimeError('合同云端不允许重定向')
    return response


def list_contracts(page=1, state=''):
    with client() as remote:
        return checked(remote.get(CONTRACTS_PATH, params={'page': page, 'state': state})).json()


def prepare_preview(revision_id: str):
    # Locate an immutable revision from the cloud; never trust a browser-provided payload.
    with client() as remote:
        revision_path = f'{CONTRACTS_PATH}/{revision_id}'
        row = checked(remote.get(revision_path)).json()
        if row['state'] != 'submitted':
            return row
        if row['templateVersion'] != 'dealer-contract-v1':
            raise ValueError('模板版本不支持')
        payload = row['payload']
        if hashlib.sha256(payload.encode('utf-8')).hexdigest() != row['payloadHash']:
            raise ValueError('合同数据摘要不匹配')
        docx, template_hash = render(json.loads(payload))
        if not 0 < len(docx) <= 2000000:
            raise ValueError('附件大小超出范围')
        # The selected production bridge is Spring/MySQL, whose preview endpoint
        # accepts one validated DOCX body. CloudBase chunk endpoints are not part
        # of this contract-order protocol and would return 404 here.
        metadata = {'payloadHash': row['payloadHash'], 'templateHash': template_hash,
                    'docxBase64': base64.b64encode(docx).decode('ascii')}
        return checked(remote.post(revision_path + '/preview', json=metadata)).json()


def preview_file(revision_id: str, expected_hash: str):
    with client() as remote:
        content = checked(remote.get(f'{CONTRACTS_PATH}/{revision_id}/preview')).content
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError('预览版本已变化，请刷新后重新查看')
        return content


def review(revision_id: str, preview_hash: str, decision: str, actor: str, note: str):
    with client() as remote:
        return checked(remote.post(f'{CONTRACTS_PATH}/{revision_id}/review', json={'previewHash': preview_hash, 'decision': decision, 'reviewer': actor, 'note': note})).json()
