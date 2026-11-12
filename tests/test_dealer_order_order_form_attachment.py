"""转合同时把系统生成的订货单归档到合同附件的单元测试。"""
from unittest.mock import patch

from api.routes import dealer_orders


def test_attach_order_form_skips_when_no_document():
    with patch('crud.local_contract_drafts.latest_document', return_value=None):
        assert dealer_orders._attach_order_form_to_contracts(
            'DO-1', ['HT-1'], '客户甲', 'boss'
        ) == []


def test_attach_order_form_saves_once_per_contract_and_dedups():
    document = (b'PK-test-docx', 'DO-2-订货单.docx')
    saved = []

    def fake_save(buffer, customer, contract_id, operator, convert_to_docx=True):
        saved.append((contract_id, buffer.getvalue(), getattr(buffer, 'name', ''), customer, operator, convert_to_docx))
        return True, '上传成功'

    with (
        patch('crud.local_contract_drafts.latest_document', return_value=document),
        patch('core.file_manager.contract_file_exists', side_effect=lambda cid, fn: cid == 'HT-DUP'),
        patch('core.file_manager.save_contract_file', side_effect=fake_save),
    ):
        attached = dealer_orders._attach_order_form_to_contracts(
            'DO-2', ['HT-1', 'HT-DUP', ' '], '客户甲', 'boss'
        )

    assert attached == ['HT-1']
    assert saved == [('HT-1', b'PK-test-docx', 'DO-2-订货单.docx', '客户甲', 'boss', False)]


def test_attach_order_form_renders_each_contract_with_its_contract_no():
    """每张新合同的订货单附件都要写入自己的合同号。"""
    calls = []
    saved = []

    def fake_latest_document(order_no, customer_name='', field_overrides=None):
        calls.append((order_no, customer_name, dict(field_overrides or {})))
        contract_no = str((field_overrides or {}).get('contract_no') or '')
        return f'PK-{contract_no}'.encode(), 'DO-5-订货单.docx'

    def fake_save(buffer, customer, contract_id, operator, convert_to_docx=True):
        saved.append((contract_id, buffer.getvalue()))
        return True, '上传成功'

    with (
        patch('crud.local_contract_drafts.latest_document', side_effect=fake_latest_document),
        patch('core.file_manager.contract_file_exists', return_value=False),
        patch('core.file_manager.save_contract_file', side_effect=fake_save),
    ):
        attached = dealer_orders._attach_order_form_to_contracts(
            'DO-5', ['HT-A', 'HT-B'], '客户甲', 'boss'
        )

    assert attached == ['HT-A', 'HT-B']
    assert [item['contract_no'] for _, _, item in calls] == ['HT-A', 'HT-B']
    assert saved == [('HT-A', b'PK-HT-A'), ('HT-B', b'PK-HT-B')]


def test_attach_order_form_does_not_break_conversion_on_failure():
    document = (b'PK-test-docx', 'DO-3-订货单.docx')
    with (
        patch('crud.local_contract_drafts.latest_document', return_value=document),
        patch('core.file_manager.contract_file_exists', return_value=False),
        patch('core.file_manager.save_contract_file', side_effect=RuntimeError('disk full')),
    ):
        assert dealer_orders._attach_order_form_to_contracts(
            'DO-3', ['HT-9'], '客户甲', 'boss'
        ) == []


def test_sync_cloud_attachments_returns_summary_and_swallows_errors():
    summary = {'orders': 1, 'synced': 2, 'skipped': 0, 'failed': 0, 'errors': []}
    with patch('api.routes.dealer_orders.sync_cloud_order_attachments', return_value=summary) as sync_mock:
        assert dealer_orders._sync_cloud_attachments_for_order('DO-4') == summary
    sync_mock.assert_called_once_with([{'order_no': 'DO-4', 'updated_at': ''}])

    with patch('api.routes.dealer_orders.sync_cloud_order_attachments', side_effect=RuntimeError('cloud 401')):
        assert dealer_orders._sync_cloud_attachments_for_order('DO-4') == {}

