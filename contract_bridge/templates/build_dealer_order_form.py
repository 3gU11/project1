# -*- coding: utf-8 -*-
"""生成「瑞钧科技办事处订货单」模板 dealer-order-form-v1.docx。

版式依据 2026-10-23 提供的正式纸质订货单还原：
- A4 纵向，左右页边距 2.5cm，表格宽 16cm
- 7 列网格 + 按行合并，保证各行分隔线位置与原件一致
- 值单元格里放 {{字段}} 占位符，由 contract_bridge.renderer.render_order_form 替换

用法：python build_dealer_order_form.py [输出路径]
"""
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

FONT = '宋体'
BODY_PT = 12
TITLE_PT = 22
DEFAULT_OUTPUT = Path(__file__).with_name('dealer-order-form-v1.docx')

# 7 列网格：把原件上出现过的所有竖线位置都保留，合并后各行分隔线才能对齐
COL_WIDTHS = [Cm(1.31), Cm(3.10), Cm(0.84), Cm(2.51), Cm(3.22), Cm(2.63), Cm(2.39)]

CENTER = WD_ALIGN_PARAGRAPH.CENTER
LEFT = WD_ALIGN_PARAGRAPH.LEFT


def style_run(run, size=BODY_PT, bold=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = FONT
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), FONT)


def write_cell(cell, text, align=LEFT, bold=False, size=BODY_PT, indent=0.0):
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    para = cell.paragraphs[0]
    para.alignment = align
    fmt = para.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    if indent:
        fmt.left_indent = Cm(indent)
    lines = str(text).split('\n')
    for index, line in enumerate(lines):
        run = para.add_run(line)
        style_run(run, size=size, bold=bold)
        if index < len(lines) - 1:
            run.add_break()


def set_table_borders(table, inner_sz=6, outer_sz=12):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), str(outer_sz if edge in ('top', 'left', 'bottom', 'right') else inner_sz))
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), '000000')
        borders.append(el)
    tbl_pr.append(borders)


def fix_layout(table):
    layout = OxmlElement('w:tblLayout')
    layout.set(qn('w:type'), 'fixed')
    table._tbl.tblPr.append(layout)


def build(target: Path = DEFAULT_OUTPUT, placeholders: bool = True) -> Path:
    """placeholders=True 生成渲染用模板（值单元格放 {{字段}}）；
    False 生成纯空白表单，给人看/打印用。"""
    doc = Document()

    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(1.8)

    title = doc.add_paragraph()
    title.alignment = CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(14)
    style_run(title.add_run('瑞钧科技办事处订货单'), size=TITLE_PT, bold=True)

    rows, cols = 19, len(COL_WIDTHS)
    table = doc.add_table(rows=rows, cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for index, width in enumerate(COL_WIDTHS):
        table.columns[index].width = width
    fix_layout(table)
    set_table_borders(table)

    heights = {
        0: 1.15, 1: 1.15, 2: 1.15, 3: 1.05,
        4: 1.05, 5: 1.05, 6: 1.05, 7: 1.05,
        8: 1.25, 9: 1.15, 10: 1.45,
        11: 1.10, 12: 1.10, 13: 1.10, 14: 1.10,
        15: 1.10, 16: 1.10, 17: 1.10,
        18: 1.60,
    }
    for index, height in heights.items():
        table.rows[index].height = Cm(height)
        table.rows[index].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST

    def merge(r1, c1, r2, c2):
        return table.cell(r1, c1).merge(table.cell(r2, c2))

    merge(0, 0, 0, 1); merge(0, 2, 0, 6)
    merge(1, 0, 1, 1); merge(1, 2, 1, 6)
    merge(2, 0, 2, 1); merge(2, 2, 2, 3); merge(2, 5, 2, 6)
    for row in (3, 4, 5, 6, 7):
        merge(row, 0, row, 1); merge(row, 2, row, 4)
    for row in (8, 9, 10):
        merge(row, 0, row, 1); merge(row, 2, row, 6)
    merge(11, 0, 14, 0)
    merge(15, 0, 17, 0)
    merge(18, 1, 18, 6)
    for row in list(range(11, 15)) + list(range(15, 18)):
        merge(row, 1, row, 2)
        merge(row, 3, row, 6)

    # 固定标签
    write_cell(table.cell(0, 0), '供方', CENTER)
    write_cell(table.cell(1, 0), '需方', CENTER)
    write_cell(table.cell(2, 0), '所属办事处', CENTER)
    write_cell(table.cell(2, 4), '签订时间', CENTER)
    for column, text in ((0, '产品名称'), (2, '规格型号'), (5, '数量'), (6, '税票')):
        write_cell(table.cell(3, column), text, CENTER)
    write_cell(table.cell(8, 0), '备注', CENTER)
    write_cell(table.cell(9, 0), '交货时间', CENTER)
    write_cell(table.cell(10, 0), '结算方式', CENTER)
    write_cell(table.cell(11, 0), '购\n货\n方\n信\n息', CENTER)
    write_cell(table.cell(15, 0), '办\n事\n处\n信\n息', CENTER)
    for offset, label in enumerate(('名称', '地址', '联系人', '联系方式')):
        write_cell(table.cell(11 + offset, 1), label, CENTER)
    for offset, label in enumerate(('办事处', '联系人', '联系方式')):
        write_cell(table.cell(15 + offset, 1), label, CENTER)
    write_cell(table.cell(18, 0), '其他\n特殊\n要求', CENTER)

    # 值单元格：placeholders=True 时放 {{字段}} 占位符，渲染时整体替换；否则留空
    def value(key: str) -> str:
        return f'{{{{{key}}}}}' if placeholders else ''

    write_cell(table.cell(0, 2), value('supplier_name') or '苏州瑞钧智能科技有限公司', CENTER)
    write_cell(table.cell(1, 2), value('dealer_name'), CENTER)
    write_cell(table.cell(2, 2), value('office_name'), CENTER)
    write_cell(table.cell(2, 5), value('signed_date'), CENTER)

    for index in range(4):
        row = 4 + index
        n = index + 1
        write_cell(table.cell(row, 0), value(f'item{n}_product'), CENTER)
        write_cell(table.cell(row, 2), value(f'item{n}_spec'), CENTER)
        write_cell(table.cell(row, 5), value(f'item{n}_qty'), CENTER)
        write_cell(table.cell(row, 6), value(f'item{n}_tax'), CENTER)

    write_cell(table.cell(8, 2), value('remark'), LEFT, indent=0.15)
    write_cell(table.cell(9, 2), value('delivery_date'), LEFT, indent=0.15)
    write_cell(table.cell(10, 2), value('settlement_terms'), LEFT, indent=0.15)

    for offset, key in enumerate(('buyer_name', 'buyer_address', 'contact_name', 'contact_phone')):
        write_cell(table.cell(11 + offset, 3), value(key), LEFT, indent=0.15)
    for offset, key in enumerate(('office_branch', 'office_contact', 'office_phone')):
        write_cell(table.cell(15 + offset, 3), value(key), LEFT, indent=0.15)

    write_cell(table.cell(18, 1), value('special_requirements'), LEFT, indent=0.15)

    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return target


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    blank = '--blank' in sys.argv
    if args:
        out = Path(args[0])
    else:
        out = (Path(__file__).resolve().parents[2] / 'docs' / '订货单模板' / '瑞钧科技办事处订货单.docx'
               if blank else DEFAULT_OUTPUT)
    print('saved ->', build(out, placeholders=not blank))
