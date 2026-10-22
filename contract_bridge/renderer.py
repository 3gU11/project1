from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.dom import minidom
import hashlib

TEMPLATE = Path(__file__).parent / 'templates' / 'dealer-contract-v1.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'




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
