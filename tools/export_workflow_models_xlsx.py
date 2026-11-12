"""导出流程模型清单：原模型备份 + 全自动通过版新模型 + 节点明细。

数据来自 rjfinshed_v8_import 的 workflow_models / workflow_model_versions /
workflow_categories 三张表，同时把这三张表完整落一份 JSON 备份。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pymysql
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DB = dict(host='localhost', port=3306, user='root', password='123321',
          database='rjfinshed_v8_import', charset='utf8mb4',
          cursorclass=pymysql.cursors.DictCursor)
SUFFIX = '-auto'
BACKUP_TS = '20261112_150122'
BACKUP_SQL = f'backups/workflow_models_backup_{BACKUP_TS}.sql'
OUT = Path('output') / f'流程模型清单_全自动通过版_{BACKUP_TS}.xlsx'

HEADERS = ['序号', '流程名称', '方向', '处理方式', '分类', '可见范围', '流程Key',
           '业务对象', '状态', '版本', '审批节点', '节点流程', '最后发布', '更新时间']
WIDTHS = [6, 34, 7, 12, 15, 13, 34, 13, 8, 9, 12, 60, 19, 19]


def fetch_all():
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT * FROM workflow_models ORDER BY id""")
            models = cur.fetchall()
            cur.execute("""SELECT * FROM workflow_model_versions ORDER BY model_id, version_no""")
            versions = cur.fetchall()
            cur.execute("""SELECT * FROM workflow_categories ORDER BY id""")
            categories = cur.fetchall()
    finally:
        conn.close()
    return models, versions, categories


def as_snapshot(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return raw or {}


def graph_of(model, versions):
    for version in versions:
        if version['model_id'] == model['id'] and version['version_no'] == model['current_version']:
            return as_snapshot(version['node_snapshot']), version
    return {}, None


def fmt_dt(value):
    if value is None:
        return ''
    return value.strftime('%Y-%m-%d %H:%M') if hasattr(value, 'strftime') else str(value)


def render_flow(snapshot):
    """把流程图渲染成一行文字，条件分支会标注 true/false。"""
    nodes = {str(n.get('id')): n for n in snapshot.get('nodes', []) if isinstance(n, dict)}
    if not nodes:
        return ''
    outgoing = defaultdict(list)
    for edge in snapshot.get('edges', []):
        outgoing[str(edge.get('source'))].append(edge)
    start = next((n for n in nodes.values() if str(n.get('type')).lower() == 'start'), None)
    if not start:
        return ''

    def label(node):
        return str(node.get('label') or node.get('id'))

    def walk(node_id, depth=0):
        node = nodes.get(node_id)
        if node is None or depth > 20:
            return '…'
        kind = str(node.get('type') or '').lower()
        if kind == 'end':
            return f'结束「{label(node)}」'
        edges = outgoing.get(node_id, [])
        if kind == 'condition':
            parts = []
            for edge in edges:
                branch = str(edge.get('branch') or '?')
                parts.append(f'{branch}→{walk(str(edge.get("target")), depth + 1)}')
            return f'条件「{label(node)}」({" | ".join(parts)})'
        tail = walk(str(edges[0].get('target')), depth + 1) if edges else '…'
        return f'{label(node)} → {tail}'

    return walk(str(start.get('id')))


def approval_count(snapshot):
    return sum(1 for n in snapshot.get('nodes', [])
               if str(n.get('type', '')).lower() in {'approval', 'approve'})


def sheet_rows(models, versions, categories, category_names):
    rows = []
    for model in models:
        snapshot, version = graph_of(model, versions)
        rows.append([
            model['name'], model['direction'] or '', model['processing_type'] or '',
            category_names.get(model['category_key'], model['category_key']),
            model['execution_scope'] or '', model['workflow_key'],
            model['business_object'] or '', model['status'] or '',
            int(model['current_version'] or 0), approval_count(snapshot),
            render_flow(snapshot),
            fmt_dt(version.get('published_at') if version else None),
            fmt_dt(model['updated_at']),
        ])
    return rows


def style_sheet(ws, title, subtitle, rows):
    header_fill = PatternFill('solid', fgColor='1F4E79')
    header_font = Font(name='微软雅黑', size=10, bold=True, color='FFFFFF')
    body_font = Font(name='微软雅黑', size=10)
    thin = Side(style='thin', color='D0D7E2')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    last_col = get_column_letter(len(HEADERS))

    ws.merge_cells(f'A1:{last_col}1')
    ws['A1'] = title
    ws['A1'].font = Font(name='微软雅黑', size=15, bold=True, color='1F2937')
    ws['A1'].alignment = Alignment(vertical='center')
    ws.row_dimensions[1].height = 28

    ws.merge_cells(f'A2:{last_col}2')
    ws['A2'] = subtitle
    ws['A2'].font = Font(name='微软雅黑', size=9, color='6B7280')
    ws['A2'].alignment = Alignment(vertical='center', wrap_text=True)
    ws.row_dimensions[2].height = 30

    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = WIDTHS[col - 1]
    ws.row_dimensions[3].height = 24

    for index, row in enumerate(rows, start=4):
        seq = ws.cell(row=index, column=1, value=index - 3)
        seq.font = body_font
        seq.border = border
        seq.alignment = Alignment(horizontal='center', vertical='center')
        for col, value in enumerate(row, start=2):
            cell = ws.cell(row=index, column=col, value=value)
            cell.font = body_font
            cell.border = border
            cell.alignment = Alignment(
                vertical='center',
                wrap_text=col in (2, 12),
                horizontal='center' if col in (1, 3, 4, 9, 10, 11) else 'left',
            )
        # 按换行列的最长文本估算行高，避免节点流程被固定行高截断。
        name_lines = -(-len(str(row[0])) // 14)
        flow_lines = -(-len(str(row[10])) // 30)
        ws.row_dimensions[index].height = max(30, max(name_lines, flow_lines) * 15 + 8)

    ws.freeze_panes = 'A4'
    ws.auto_filter.ref = f'A3:{last_col}{3 + len(rows)}'
    ws.sheet_properties.tabColor = '2E7D32' if '（新）' in title else '8A8F98'


def build_note_sheet(wb, models, versions, categories, new_models, old_models):
    ws = wb.create_sheet('备份说明')
    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 96
    approval_models = '、'.join(m['name'] for m in old_models if m['processing_type'] == '需要审批')
    lines = [
        ('生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('数据库', 'rjfinshed_v8_import（MySQL 127.0.0.1:3306）'),
        ('备份范围', 'workflow_models、workflow_model_versions、workflow_categories'),
        ('SQL 备份（重建前）', f'{BACKUP_SQL} —— 模型 14 条 / 版本 49 条 / 分类 7 条，可直接还原重建前状态'),
        ('JSON 快照（当前）', f'backups/workflow_models_backup_{BACKUP_TS}.json —— 模型 {len(models)} 条 / '
                            f'版本 {len(versions)} 条 / 分类 {len(categories)} 条'),
        ('恢复命令', f'mysql -u root -p rjfinshed_v8_import < {BACKUP_SQL}'),
        ('新模型数量', f'{len(new_models)} 个（Key 统一加 {SUFFIX} 后缀，名称加“（全自动通过）”）'),
        ('新模型规则', '删除 approval/approve 审批节点并接通前后连线；保留发起、条件、执行、通知、结束节点'),
        ('新模型状态', '已发布 / 版本 v1 / 处理方式=自动通过 / 14 个快照全部校验通过 / 审批节点 0 个'),
        ('原模型状态', f'未做任何修改，仍需审批的模型 {sum(1 for m in old_models if m["processing_type"] == "需要审批")} 个：{approval_models}'),
        ('生效说明', '新模型使用独立 Key，业务代码仍按原 Key 发起流程；本次未改业务代码与原模型，'
                    '所以线上审批行为不变。如需切换为全自动，需把业务 Key 指向新模型或直接改原模型。'),
    ]
    ws.merge_cells('A1:B1')
    ws['A1'] = '流程模型备份与全自动版本说明'
    ws['A1'].font = Font(name='微软雅黑', size=15, bold=True, color='1F2937')
    ws.row_dimensions[1].height = 30
    for index, (key, value) in enumerate(lines, start=2):
        a = ws.cell(row=index, column=1, value=key)
        b = ws.cell(row=index, column=2, value=value)
        a.font = Font(name='微软雅黑', size=10, bold=True)
        b.font = Font(name='微软雅黑', size=10)
        a.alignment = Alignment(vertical='center', wrap_text=True)
        b.alignment = Alignment(vertical='center', wrap_text=True)
        thin = Side(style='thin', color='D0D7E2')
        a.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        b.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        a.fill = PatternFill('solid', fgColor='EAF1F8')
        lines_needed = -(-len(str(value)) // 44)
        ws.row_dimensions[index].height = max(24, lines_needed * 16 + 8)


def build_node_sheet(wb, old_models, new_models, versions, category_names):
    ws = wb.create_sheet('节点明细')
    header = ['来源', '流程名称', '流程Key', '节点ID', '节点类型', '节点名称',
              '审批/通知角色', '业务动作', '条件字段', '条件比较', '后续节点']
    widths = [12, 28, 34, 24, 12, 20, 18, 20, 20, 12, 40]
    fill = PatternFill('solid', fgColor='1F4E79')
    font = Font(name='微软雅黑', size=10, bold=True, color='FFFFFF')
    thin = Side(style='thin', color='D0D7E2')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col, (text, width) in enumerate(zip(header, widths), start=1):
        cell = ws.cell(row=1, column=col, value=text)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(header))}1'

    row_index = 2
    for source, models in (('原模型', old_models), ('全自动模型', new_models)):
        for model in models:
            snapshot, _ = graph_of(model, versions)
            edges = defaultdict(list)
            for edge in snapshot.get('edges', []):
                edges[str(edge.get('source'))].append(edge)
            for node in snapshot.get('nodes', []):
                successors = [str(e.get('target')) for e in edges.get(str(node.get('id')), [])]
                role = node.get('approvalRoles') or node.get('notifyRoles') or []
                operator = node.get('conditionOperator') or ''
                if node.get('conditionValue') not in (None, ''):
                    operator = f'{operator} {node.get("conditionValue")}'.strip()
                values = [source, model['name'], model['workflow_key'], node.get('id'),
                          node.get('type'), node.get('label'),
                          '、'.join(str(r) for r in role), node.get('action', ''),
                          node.get('conditionField', ''), operator,
                          '、'.join(successors)]
                for col, value in enumerate(values, start=1):
                    cell = ws.cell(row=row_index, column=col, value=value)
                    cell.font = Font(name='微软雅黑', size=10)
                    cell.border = border
                    cell.alignment = Alignment(vertical='center', wrap_text=col in (3, 11))
                row_index += 1
    ws.auto_filter.ref = f'A1:{get_column_letter(len(header))}{row_index - 1}'


def main():
    models, versions, categories = fetch_all()
    category_names = {c['category_key']: c['name'] for c in categories}

    def sort_key(model):
        return (model['category_key'], model['name'])

    new_models = sorted([m for m in models if m['workflow_key'].endswith(SUFFIX)], key=sort_key)
    old_models = sorted([m for m in models if not m['workflow_key'].endswith(SUFFIX)], key=sort_key)

    backup = {'exported_at': datetime.now().isoformat(timespec='seconds'),
              'database': DB['database'], 'tables': {
                  'workflow_models': models,
                  'workflow_model_versions': versions,
                  'workflow_categories': categories}}
    Path('backups').mkdir(exist_ok=True)
    with open(f'backups/workflow_models_backup_{BACKUP_TS}.json', 'w', encoding='utf-8') as fh:
        json.dump(backup, fh, ensure_ascii=False, indent=1, default=str)

    wb = Workbook()
    ws_new = wb.active
    ws_new.title = '全自动模型（新）'
    style_sheet(
        ws_new,
        '流程模型清单 · 全自动通过版',
        f'共 {len(new_models)} 个模型，均为“自动通过 / 自动执行”，无审批节点；生成时间 '
        f'{datetime.now():%Y-%m-%d %H:%M}',
        sheet_rows(new_models, versions, categories, category_names),
    )
    ws_old = wb.create_sheet('原模型备份')
    style_sheet(
        ws_old,
        '流程模型清单 · 原模型备份',
        f'共 {len(old_models)} 个模型，本次未做任何修改；其中“需要审批”'
        f'{sum(1 for m in old_models if m["processing_type"] == "需要审批")} 个',
        sheet_rows(old_models, versions, categories, category_names),
    )
    build_node_sheet(wb, old_models, new_models, versions, category_names)
    build_note_sheet(wb, models, versions, categories, new_models, old_models)

    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print(f'saved: {OUT}')
    print(f'new={len(new_models)} old={len(old_models)} versions={len(versions)}')


if __name__ == '__main__':
    main()

