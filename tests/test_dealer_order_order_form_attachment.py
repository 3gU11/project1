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
