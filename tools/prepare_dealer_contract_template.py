from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SOURCE = Path(r"D:\firefox download\南通泽旺凯合同.docx")
DESTINATION = Path(__file__).resolve().parents[1] / "合同" / "templates" / "dealer-contract.docx"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}
ET.register_namespace("w", WORD_NS)


def tag(name: str) -> str:
    return f"{{{WORD_NS}}}{name}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))


def replace_paragraph(paragraph: ET.Element, value: str) -> None:
    text_nodes = paragraph.findall(".//w:t", NS)
    if not text_nodes:
        run = ET.SubElement(paragraph, tag("r"))
        node = ET.SubElement(run, tag("t"))
        node.text = value
        return
    text_nodes[0].text = value
    text_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for node in text_nodes[1:]:
        node.text = ""


def set_cell_text(cell: ET.Element, value: str) -> None:
    paragraphs = cell.findall("./w:p", NS)
    if not paragraphs:
        paragraphs = [ET.SubElement(cell, tag("p"))]
    replace_paragraph(paragraphs[0], value)
    for paragraph in paragraphs[1:]:
        replace_paragraph(paragraph, "")


def set_paragraph_containing(root: ET.Element, needle: str, value: str) -> None:
    for paragraph in root.findall(".//w:p", NS):
        if needle in paragraph_text(paragraph):
            replace_paragraph(paragraph, value)
            return
    raise ValueError(f"Template paragraph not found: {needle}")


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)

    with zipfile.ZipFile(SOURCE, "r") as source_zip:
        document = ET.fromstring(source_zip.read("word/document.xml"))
        paragraphs = document.findall(".//w:p", NS)
        # Replace sample identifying details while preserving paragraph styling.
        paragraph_replacements = {
            "签订时间：2026年1月27日": "签订时间：{{sign_date}}",
            "合同编号：": "合同编号：{{contract_no}}",
            "如皋江安镇镇南路41号": "{{buyer_address}}",
            "刘兴平": "{{buyer_contact}}",
            "18068058159": "{{buyer_phone}}",
            "一、交（提）货时间： 2026年3月2日": "一、交（提）货时间：{{delivery_date}}",
            "二、结算方式及期限：  欠6万，10个月清。": "二、结算方式及期限：{{payment_terms}}",
        }
        for paragraph in paragraphs:
            text = paragraph_text(paragraph)
            for old, new in paragraph_replacements.items():
                if old in text:
                    replace_paragraph(paragraph, text.replace(old, new))
                    break
        set_paragraph_containing(document, "需方：", "需方：{{buyer_name}}　合同编号：{{contract_no}}")
        for paragraph in document.findall(".//w:p", NS):
            if "泽旺凯机械（如皋）有限公司" in paragraph_text(paragraph):
                replace_paragraph(paragraph, "")
                break

        tables = document.findall(".//w:tbl", NS)
        if len(tables) < 3:
            raise ValueError("Expected product, buyer-detail, and signature tables")

        product_rows = tables[0].findall("./w:tr", NS)
        if len(product_rows) < 5:
            raise ValueError("Expected four product rows in the product table")
        for index, row in enumerate(product_rows[1:5], start=1):
            cells = row.findall("./w:tc", NS)
            if len(cells) < 6:
                raise ValueError("Product table row has fewer than six cells")
            set_cell_text(cells[2], f"{{{{item_{index}_model}}}}")
            set_cell_text(cells[4], f"{{{{item_{index}_quantity}}}}")
            set_cell_text(cells[5], f"{{{{item_{index}_price}}}}")

        buyer_rows = tables[1].findall("./w:tr", NS)
        buyer_fields = [
            (0, 1, "{{buyer_name}}"),
            (0, 3, "{{buyer_address}}"),
            (1, 1, "{{buyer_contact}}"),
            (1, 3, "{{buyer_phone}}"),
            (2, 1, "{{special_requirements}}"),
            (2, 3, "{{remarks}}"),
        ]
        for row_index, cell_index, value in buyer_fields:
            cells = buyer_rows[row_index].findall("./w:tc", NS)
            set_cell_text(cells[cell_index], value)

        signature_rows = tables[2].findall("./w:tr", NS)
        # The final two-cell table contains the buyer signature block.
        buyer_cell = signature_rows[0].findall("./w:tc", NS)[1]
        signature_fields = [
            "单位名称(章)：{{buyer_name}}",
            "单位地址：{{buyer_address}}",
            "法定代表人：{{legal_representative}}",
            "委托代理人：{{authorized_agent}}",
            "开户银行：{{buyer_bank}}",
            "帐　　号：{{buyer_bank_account}}",
            "税　　号：{{buyer_tax_no}}",
            "电　　话：{{buyer_phone}}",
            "传　　真：{{buyer_fax}}",
        ]
        signature_paragraphs = buyer_cell.findall("./w:p", NS)
        if not signature_paragraphs:
            signature_paragraphs = [ET.SubElement(buyer_cell, tag("p"))]
        while len(signature_paragraphs) < len(signature_fields):
            signature_paragraphs.append(ET.SubElement(buyer_cell, tag("p")))
        for paragraph, value in zip(signature_paragraphs, signature_fields):
            replace_paragraph(paragraph, value)
        for paragraph in signature_paragraphs[len(signature_fields):]:
            replace_paragraph(paragraph, "")

        body_text = "\n".join(paragraph_text(p) for p in document.findall(".//w:p", NS))
        if re.search(r"18068058159|刘兴平|欠6万|镇南路41号|2026年3月2日|2026年1月27日", body_text):
            raise ValueError("Sample customer data remains in the template")

        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        temp_path = DESTINATION.with_suffix(".tmp.docx")
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for item in source_zip.infolist():
                content = source_zip.read(item.filename)
                if item.filename == "word/document.xml":
                    content = ET.tostring(document, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(item, content)
    temp_path.replace(DESTINATION)
    print(f"Prepared template: {DESTINATION}")


if __name__ == "__main__":
    main()
