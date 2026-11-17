"""生成“测试机流程模型导入包”。

输入：本机 rjfinshed_v8_import 中已生成好的 *-auto 全自动模型快照。
输出：
  output/workflow_models_auto_pass_import.sql   可直接在测试机 MySQL 执行的导入脚本
  output/workflow_models_auto_pass_import.json  同一份数据的 JSON 版本
  output/测试机流程模型导入_<ts>.xlsx            导入清单 / 节点 JSON / 导入步骤

导入按 workflow_key 覆盖原模型（原 Key 不变），并把旧版本标记为历史。
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
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OPERATOR = 'import-auto-pass'
SQL_PATH = Path('output') / 'workflow_models_auto_pass_import.sql'
JSON_PATH = Path('output') / 'workflow_models_auto_pass_import.json'
XLSX_PATH = Path('output') / f'测试机流程模型导入_{TS}.xlsx'


def fetch():
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT m.*, v.version_no, v.node_snapshot, v.published_at
                           FROM workflow_models m
                           LEFT JOIN workflow_model_versions v
                             ON v.model_id=m.id AND v.version_no=m.current_version
                           ORDER BY m.id""")
            models = cur.fetchall()
            cur.execute('SELECT * FROM workflow_categories ORDER BY id')
            categories = cur.fetchall()
    finally:
        conn.close()
    return models, categories


def as_snapshot(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or {}


def render_flow(snapshot):
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
            parts = [f'{edge.get("branch") or "?"}→{walk(str(edge.get("target")), depth + 1)}'
                     for edge in edges]
            return f'条件「{label(node)}」({" | ".join(parts)})'
        tail = walk(str(edges[0].get('target')), depth + 1) if edges else '…'
        return f'{label(node)} → {tail}'

    return walk(str(start.get('id')))


def approval_nodes(snapshot):
    return [n.get('id') for n in snapshot.get('nodes', [])
            if str(n.get('type', '')).lower() in {'approval', 'approve'}]


def sql_quote(text):
    return "'" + str(text).replace('\\', '\\\\').replace("'", "''") + "'"


def build_payload(models):
    """原 Key -> 全自动快照（取对应 *-auto 模型）。"""
    auto_by_key = {m['workflow_key'][:-len('-auto')]: m
                   for m in models if m['workflow_key'].endswith('-auto')}
    originals = [m for m in models if not m['workflow_key'].endswith('-auto')]
    payload = []
    for model in originals:
        auto = auto_by_key.get(model['workflow_key'])
        if not auto:
            raise SystemExit(f"缺少 {model['workflow_key']}-auto 的全自动快照")
        snapshot = as_snapshot(auto['node_snapshot'])
        if approval_nodes(snapshot):
            raise SystemExit(f"{model['workflow_key']} 快照仍有审批节点")
        original_nodes = {str(n.get('id')): n
                          for n in as_snapshot(model['node_snapshot']).get('nodes', [])
                          if isinstance(n, dict)}
        removed = [str(original_nodes.get(node_id, {}).get('label') or node_id)
                   for node_id in approval_nodes(as_snapshot(model['node_snapshot']))]
        payload.append({
            'workflow_key': model['workflow_key'],
            'name': model['name'],
            'category_key': model['category_key'],
            'direction': model['direction'],
            'business_object': model['business_object'],
            'execution_scope': model['execution_scope'],
            'is_required': int(model['is_required'] or 0),
            'old_processing_type': model['processing_type'],
            'removed_approval_nodes': removed,
            'node_snapshot': snapshot,
            'flow': render_flow(snapshot),
        })
    return payload


def build_sql(payload, categories):
    lines = [
        '-- ============================================================',
        '-- 流程模型导入脚本：把 14 个流程模型统一改成“自动通过 / 自动执行”',
        f'-- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}',
        '-- 目标库：测试机 MySQL（表 workflow_models / workflow_model_versions / workflow_categories）',
        '-- 执行方式：',
        '--   mysql --default-character-set=utf8mb4 -h <主机> -P 3306 -u <用户> -p <库名> '
        '< workflow_models_auto_pass_import.sql',
        '-- 说明：按 workflow_key 覆盖原模型（Key 不变），旧发布版本标记为历史，再写入新的已发布版本。',
        '-- ============================================================',
        'SET NAMES utf8mb4;',
        'START TRANSACTION;',
        '',
        '-- 1) 流程分类（不存在则补，存在则同步名称）',
    ]
    for category in categories:
        lines.append(
            'INSERT INTO workflow_categories (category_key,name,description) VALUES ('
            f"{sql_quote(category['category_key'])},{sql_quote(category['name'])},"
            f"{sql_quote(category.get('description') or '')}) "
            'ON DUPLICATE KEY UPDATE name=VALUES(name);')
    lines.append('')

    for index, item in enumerate(payload, start=1):
        key = item['workflow_key']
        snapshot_json = json.dumps(item['node_snapshot'], ensure_ascii=False, separators=(',', ':'))
        removed = '、'.join(item['removed_approval_nodes']) or '无（原本已自动通过）'
        lines += [
            f'-- {index}. {item["name"]}（{key}） 删除审批节点：{removed}',
            'INSERT INTO workflow_models',
            '  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,',
            '   status,is_required,current_version,created_by,updated_by,created_at,updated_at)',
            'VALUES (' + ', '.join([
                sql_quote(key), sql_quote(item['name']), sql_quote(item['category_key']),
                sql_quote(item['direction']), "'自动通过'", sql_quote(item['business_object']),
                sql_quote(item['execution_scope']), "'已发布'", str(item['is_required']), '0',
                sql_quote(OPERATOR), sql_quote(OPERATOR), 'NOW()', 'NOW()',
            ]) + ')',
            'ON DUPLICATE KEY UPDATE',
            '  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),',
            "  processing_type='自动通过', business_object=VALUES(business_object),",
            "  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),",
            f"  updated_by={sql_quote(OPERATOR)}, updated_at=NOW();",
            f'SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key={sql_quote(key)});',
            'SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions '
            'WHERE model_id=@model_id);',
            "UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 "
            "WHERE model_id=@model_id AND status='已发布';",
            'INSERT INTO workflow_model_versions',
            '  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)',
            'VALUES (@model_id,@next_version,\'已发布\','
            + sql_quote(snapshot_json)
            + f",1,{sql_quote(OPERATOR)},NOW(),NOW());",
            'UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;',
            '',
        ]

    lines += [
        'COMMIT;',
        '',
        '-- ============================================================',
        '-- 导入后自查（可单独执行）',
        '-- SELECT workflow_key, name, processing_type, status, current_version',
        '--   FROM workflow_models ORDER BY category_key, name;',
        '-- SELECT m.workflow_key, v.version_no, v.status, v.runtime_enabled',
        '--   FROM workflow_models m JOIN workflow_model_versions v',
        '--     ON v.model_id=m.id AND v.version_no=m.current_version',
        '--  WHERE v.runtime_enabled=1 ORDER BY m.workflow_key;',
        '-- ============================================================',
    ]
    return '\n'.join(lines) + '\n'


def style_header(ws, headers, widths, row=3):
    fill = PatternFill('solid', fgColor='1F4E79')
    font = Font(name='微软雅黑', size=10, bold=True, color='FFFFFF')
    thin = Side(style='thin', color='D0D7E2')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col, (text, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[row].height = 24
    ws.freeze_panes = f'A{row + 1}'


def build_sheet_list(wb, payload, category_names):
    ws = wb.active
    ws.title = '导入清单'
    headers = ['序号', '流程名称', '流程Key', '方向', '分类', '处理方式', '状态',
               '本次改动', '节点流程', '导入方式']
    widths = [6, 26, 30, 7, 14, 12, 8, 26, 62, 34]
    ws.merge_cells('A1:J1')
    ws['A1'] = '测试机流程模型导入清单（全部自动通过 / 自动执行）'
    ws['A1'].font = Font(name='微软雅黑', size=15, bold=True, color='1F2937')
    ws.row_dimensions[1].height = 30
    ws.merge_cells('A2:J2')
    ws['A2'] = (f'共 {len(payload)} 个模型；按 workflow_key 覆盖测试机同名模型，业务代码无需改动。'
                f'生成时间 {datetime.now():%Y-%m-%d %H:%M}')
    ws['A2'].font = Font(name='微软雅黑', size=9, color='6B7280')
    ws.row_dimensions[2].height = 22
    style_header(ws, headers, widths)

    thin = Side(style='thin', color='D0D7E2')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for index, item in enumerate(payload, start=4):
        removed = item['removed_approval_nodes']
        change = f"删除审批节点（{'、'.join(removed)}）" if removed else '无需改动（原本已自动通过）'
        values = [index - 3, item['name'], item['workflow_key'], item['direction'],
                  category_names.get(item['category_key'], item['category_key']),
                  '自动通过', '已发布', change, item['flow'],
                  '覆盖原 Key + 发布新版本']
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=index, column=col, value=value)
            cell.font = Font(name='微软雅黑', size=10,
                             bold=(col == 8 and bool(removed)))
            cell.border = border
            cell.alignment = Alignment(vertical='center', wrap_text=col in (2, 8, 9),
                                       horizontal='center' if col in (1, 4, 6, 7) else 'left')
        lines = max(-(-len(str(item['flow'])) // 30), -(-len(str(change)) // 13))
        ws.row_dimensions[index].height = max(30, lines * 15 + 8)
    ws.auto_filter.ref = f'A3:J{3 + len(payload)}'


def build_sheet_json(wb, payload):
    ws = wb.create_sheet('节点JSON')
    headers = ['序号', '流程Key', '节点数', 'node_snapshot（JSON，导入脚本使用同一份）']
    widths = [6, 30, 8, 120]
    ws.merge_cells('A1:D1')
    ws['A1'] = '模型节点数据（node_snapshot）'
    ws['A1'].font = Font(name='微软雅黑', size=14, bold=True, color='1F2937')
    ws.row_dimensions[1].height = 26
    style_header(ws, headers, widths, row=2)

    thin = Side(style='thin', color='D0D7E2')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for index, item in enumerate(payload, start=3):
        snapshot_json = json.dumps(item['node_snapshot'], ensure_ascii=False, separators=(',', ':'))
        for col, value in enumerate([index - 2, item['workflow_key'],
                                     len(item['node_snapshot'].get('nodes', [])), snapshot_json], start=1):
            cell = ws.cell(row=index, column=col, value=value)
            cell.font = Font(name='Consolas' if col == 4 else '微软雅黑', size=9)
            cell.border = border
            cell.alignment = Alignment(vertical='top', wrap_text=col == 4,
                                       horizontal='center' if col in (1, 3) else 'left')
        ws.row_dimensions[index].height = 90
    ws.auto_filter.ref = f'A2:D{2 + len(payload)}'


def build_sheet_steps(wb):
    ws = wb.create_sheet('导入步骤')
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 110
    ws.merge_cells('A1:B1')
    ws['A1'] = '测试机导入步骤'
    ws['A1'].font = Font(name='微软雅黑', size=15, bold=True, color='1F2937')
    ws.row_dimensions[1].height = 30
    steps = [
        ('准备', '把 workflow_models_auto_pass_import.sql 拷到测试机；确认能连上测试库（MySQL）。'),
        ('先备份', 'mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 '
                  '-h <主机> -u <用户> -p <库名> workflow_models workflow_model_versions '
                  'workflow_categories > workflow_models_before_import.sql'),
        ('执行导入', 'mysql --default-character-set=utf8mb4 -h <主机> -P 3306 -u <用户> -p <库名> '
                    '< workflow_models_auto_pass_import.sql'),
        ('验证 1', 'SELECT workflow_key,name,processing_type,status,current_version FROM workflow_models '
                  'ORDER BY category_key,name;  —— 14 行应全部为“自动通过 / 已发布”。'),
        ('验证 2', 'SELECT m.workflow_key,v.version_no,v.status,v.runtime_enabled FROM workflow_models m '
                  'JOIN workflow_model_versions v ON v.model_id=m.id AND v.version_no=m.current_version '
                  'WHERE v.runtime_enabled=1;  —— 14 行应为“已发布 / 1”。'),
        ('验证 3', '打开测试机“流程模型”页面刷新，14 个模型处理方式应显示“自动通过”，'
                  '点开“删除订单/取消合同”等看不到审批节点。'),
        ('生效', '无需改代码。业务提交时模型没有审批节点，实例直接置为“已通过”并执行对应业务动作。'),
        ('回滚', 'mysql ... < workflow_models_before_import.sql（覆盖回导入前的模型与版本）。'),
        ('注意 1', '脚本按 workflow_key 覆盖，可重复执行；每执行一次会多写一个已发布版本，旧版本自动转历史。'),
        ('注意 2', 'Windows 控制台请务必带 --default-character-set=utf8mb4，否则中文会乱码。'),
        ('注意 3', '脚本只改这三张表，不动流程实例、待办和业务数据；已在进行中的实例仍按原快照执行。'),
    ]
    for index, (key, text) in enumerate(steps, start=3):
        a = ws.cell(row=index, column=1, value=key)
        b = ws.cell(row=index, column=2, value=text)
        a.font = Font(name='微软雅黑', size=10, bold=True)
        b.font = Font(name='微软雅黑', size=10)
        a.alignment = Alignment(vertical='center', horizontal='center')
        b.alignment = Alignment(vertical='center', wrap_text=True)
        a.fill = PatternFill('solid', fgColor='EAF1F8')
        thin = Side(style='thin', color='D0D7E2')
        a.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        b.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        ws.row_dimensions[index].height = max(28, (-(-len(text) // 52)) * 16 + 10)


def main():
    models, categories = fetch()
    payload = build_payload(models)
    category_names = {c['category_key']: c['name'] for c in categories}

    SQL_PATH.parent.mkdir(exist_ok=True)
    SQL_PATH.write_text(build_sql(payload, categories), encoding='utf-8')
    JSON_PATH.write_text(json.dumps({
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'target': 'workflow_models / workflow_model_versions / workflow_categories',
        'mode': '按 workflow_key 覆盖原模型',
        'models': payload,
    }, ensure_ascii=False, indent=1), encoding='utf-8')

    wb = Workbook()
    build_sheet_list(wb, payload, category_names)
    build_sheet_json(wb, payload)
    build_sheet_steps(wb)
    wb.save(XLSX_PATH)

    print(f'sql   : {SQL_PATH}')
    print(f'json  : {JSON_PATH}')
    print(f'xlsx  : {XLSX_PATH}')
    print(f'models: {len(payload)}')
    print('changed:', [p['workflow_key'] for p in payload if p['removed_approval_nodes']])


if __name__ == '__main__':
    main()

