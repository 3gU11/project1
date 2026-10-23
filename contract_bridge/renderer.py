from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.dom import minidom
import hashlib
import re

TEMPLATE = Path(__file__).parent / 'templates' / 'dealer-contract-v1.docx'
ORDER_FORM_TEMPLATE = Path(__file__).parent / 'templates' / 'dealer-order-form-v1.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'

PLACEHOLDER = re.compile(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}')


def _text_of(node) -> str:
    return ''.join(child.data for child in node.childNodes if child.nodeType == child.TEXT_NODE)


def _repack(package: ZipFile, root, output: BytesIO) -> bytes:
    with ZipFile(output, 'w') as result:
        for entry in package.infolist():
            result.writestr(entry, root.toxml(encoding='UTF-8')
                            if entry.filename == 'word/document.xml' else package.read(entry.filename))
    return output.getvalue()


def render_order_form(fields: dict[str, str], template: Path = ORDER_FORM_TEMPLATE) -> tuple[bytes, str]:
    """Fill the 订货单 form by replacing {{field}} placeholders.

    The form is a pure table: every value lives in its own cell and the labels are
    fixed text, so we replace placeholders in place instead of rebuilding whole
    paragraphs (which is what render() does for the clause-style contract).
    Missing fields become empty strings, never a leftover {{placeholder}}.
    """
    source = template.read_bytes()
    with ZipFile(BytesIO(source)) as package:
        root = minidom.parseString(package.read('word/document.xml'))
        for paragraph in root.getElementsByTagNameNS(NS['w'], 'p'):
            texts = list(paragraph.getElementsByTagNameNS(NS['w'], 't'))
            if not texts:
                continue
            joined = ''.join(_text_of(text) for text in texts)
            if '{{' not in joined:
                continue
            # Word may split one placeholder across several runs; work on the
            # concatenated text and write the result back into the first run.
            filled = PLACEHOLDER.sub(lambda match: str(fields.get(match.group(1), '') or ''), joined)
            for text in texts:
                for child in list(text.childNodes):
                    text.removeChild(child)
            texts[0].appendChild(root.createTextNode(filled))
            texts[0].setAttribute('xml:space', 'preserve')
        return _repack(package, root, BytesIO()), hashlib.sha256(source).hexdigest()


def render(fields: dict[str, str], template: Path = TEMPLATE) -> tuple[bytes, str]:
    """Only bookmarked variable paragraphs change; all fixed clauses stay in place."""
    source = template.read_bytes()
    with ZipFile(BytesIO(source)) as package:
        root = minidom.parseString(package.read('word/document.xml'))
        for mark in root.getElementsByTagNameNS(NS['w'], 'bookmarkStart'):
            key = mark.getAttributeNS(NS['w'], 'name').removeprefix('ct_')
            paragraph = mark.parentNode
            texts = list(paragraph.getElementsByTagNameNS(NS['w'], 't'))
            old = ''.join(''.join(t.data for t in text.childNodes if t.nodeType == t.TEXT_NODE) for text in texts)
            value = fields.get(key, '')
            if key == 'supplier_header':
                value = f"供方：{fields['supplier_name']}    合同编号：{fields['contract_no']}"
            elif key == 'buyer_header':
                value = f"需方：{fields['buyer_name']}    签订地点：{fields['signing_place']}"
            elif key == 'signed_date':
                value = old.split('签订时间：')[0] + '签订时间：' + fields['signed_date']
            elif key in ('delivery_date', 'settlement_terms', 'total_upper') or '_signature_' in key:
                # Keep every existing label; dual phone/fax field uses two separate values.
                if key == 'supplier_signature_7':
                    parts = value.split('|')
                    value = '电话：' + parts[0] + '    传真：' + (parts[1] if len(parts)>1 else '')
                else:
                    value = old.split('：')[0] + '：' + value
            if texts:
                for text in texts:
                    for child in list(text.childNodes):
                        text.removeChild(child)
                texts[0].appendChild(root.createTextNode(value))
                texts[0].setAttribute('xml:space', 'preserve')
            else:
                run = root.createElementNS(NS['w'], 'w:r')
                paragraph.appendChild(run)
                text = root.createElementNS(NS['w'], 'w:t')
                run.appendChild(text)
                text.appendChild(root.createTextNode(value))
        output = BytesIO()
        with ZipFile(output, 'w') as result:
            for entry in package.infolist():
                result.writestr(entry, root.toxml(encoding='UTF-8') if entry.filename == 'word/document.xml' else package.read(entry.filename))
    return output.getvalue(), hashlib.sha256(source).hexdigest()
