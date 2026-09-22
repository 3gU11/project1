"""Create an isolated demonstration database; never replace an existing database."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, text
from database import get_engine
from config import DEFAULT_ROLE_PERMISSIONS
from crud.roles import PERMISSION_CODES

TABLES = '''model_dictionary roles role_permissions users user_sessions
finished_goods_data sales_orders factory_plan plan_import import_staging
transaction_log sys_operation_log audit_log operation_log contract_records
inbound_history shipping_history warehouse_layout production_lines batches units
production_history_ledger production_queue planning_records rush_order_queue
forecast_batch_slots sandbox_batch_baselines sandbox_batch_changes
sandbox_batch_sync_status sandbox_recompute_jobs system_config schema_version
dealer_applications dealer_orders dealer_order_sync_events cloud_sync_outbox
photo_item_library model_photo_config ocr_field_rules machine_photo_tasks
machine_photo_files machine_photo_ocr_results machine_photo_submissions
machine_component_bindings repair_component_replacement_events'''.split()


def validate_target(name, source):
    if not re.fullmatch(r'v8_demo_[a-zA-Z0-9_]+', name) or name == source:
        raise ValueError('Target must be a separate v8_demo_* database')


def insert(conn, table, row):
    keys = list(row)
    conn.execute(text(f"INSERT INTO `{table}` ({','.join('`'+k+'`' for k in keys)}) "
                      f"VALUES ({','.join(':v'+str(i) for i in range(len(keys)))})"),
                 {'v'+str(i): row[k] for i, k in enumerate(keys)})


def create_demo(name):
    source_engine = get_engine()
    source = source_engine.url.database
    validate_target(name, source)
    # Only metadata and the explicitly requested dictionary are read from the source.
    with source_engine.connect() as src:
        if src.execute(text('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=:n'), {'n': name}).scalar():
            raise ValueError(f'{name} already exists; choose a new name (existing data is never reset)')
        models = [dict(r) for r in src.execute(text('SELECT * FROM model_dictionary ORDER BY sort_order,id')).mappings()]
        enabled = [m for m in models if m['enabled']]
        if not enabled:
            raise ValueError('Source dictionary has no enabled models')
        available = set(src.execute(text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=:n AND TABLE_TYPE='BASE TABLE'"), {'n': source}).scalars())
        missing = set(TABLES) - available
        if missing:
            raise ValueError(f'Missing schema tables: {sorted(missing)}')
        src.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci'))
        for table in TABLES:
            src.execute(text(f'CREATE TABLE `{name}`.`{table}` LIKE `{source}`.`{table}`'))
    engine = create_engine(source_engine.url.set(database=name))
    now = datetime.now().replace(microsecond=0)
    with engine.begin() as c:
        for row in models:
            insert(c, 'model_dictionary', row)
        for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            if role == 'Admin':
                permissions = sorted(PERMISSION_CODES)
            insert(c, 'roles', {'role_id': role, 'role_name': '演示'+role})
            for permission in permissions:
                insert(c, 'role_permissions', {'role_id': role, 'func_code': permission})
            insert(c, 'users', {'username': 'demo_'+role.lower(), 'password': 'Demo123456', 'role': role,
                               'name': '测试'+role, 'status': 'active', 'register_time': now})
        insert(c, 'system_config', {'config_key': 'demo_database', 'config_value': 'synthetic-v1', 'description': '功能演示专用，业务数据均为虚构'})
        slots = []
        for i in range(len(enabled)):
            slots.append({'code': f'A{i+1:02}', 'x': (i % 6)*180, 'y': (i//6)*200, 'w': 160, 'h': 180, 'locked': False})
        insert(c, 'warehouse_layout', {'layout_id': 'default', 'layout_json': json.dumps({'slots': slots}, ensure_ascii=False), 'update_time': now})
        for i, model in enumerate(enabled, 1):
            m = model['model_name']
            customer, dealer = f'测试客户{i:02}有限公司', f'测试代理商{i:02}'
            slot = f'A{i:02}'
            line = f'DEMO-LINE-{i:02}'
            insert(c, 'production_lines', {'line_id': line, 'line_name': f'演示产线{i:02}', 'status': 'Busy', 'display_order': i, 'model_type': m, 'region': '演示车间', 'current_batch_id': f'DEMO-B-{i:02}-P'})
            for scenario, batch_status in [('C', 'Completed'), ('P', 'In_Production'), ('Q', 'Confirmed')]:
                batch = f'DEMO-B-{i:02}-{scenario}'
                count = 4 if scenario == 'C' else 2
                due = now + timedelta(days=7 if scenario != 'C' else -7)
                insert(c, 'batches', {'batch_id': batch, 'batch_no': i*10+'CPQ'.index(scenario), 'batch_code': batch,
                       'model_type': m, 'major_category': model['model_family'], 'base_capacity': count, 'capacity': count,
                       'status': batch_status, 'source': 'manual', 'production_line_id': line if scenario == 'P' else None,
                       'expected_inbound_date': due.date(), 'due_date_start': due.date(), 'due_date_end': due.date()})
                for j in range(1, count+1):
                    sn = f'DEMO-{i:02}-{scenario}-{j:03}'
                    order = f'DEMO-SO-{i:02}-{scenario}-{j}'
                    contract = f'DEMO-HT-{i:02}-{scenario}-{j}'
                    allocated = (scenario == 'C' and j >= 3) or (scenario == 'P' and j == 1)
                    shipped = scenario == 'C' and j == 4
                    fg_status = ('已出库' if shipped else '待发货' if allocated else '库存中') if scenario == 'C' else '待入库'
                    insert(c, 'units', {'unit_id': sn, 'serial_no': sn, 'batch_id': batch, 'slot_index': j, 'model_type': m,
                           'production_line_id': line if scenario == 'P' else None, 'status': batch_status,
                           'contract_no': contract if allocated else '', 'customer': customer if allocated else '',
                           'dealer_name': dealer if allocated else '', 'due_date': due.date(), 'order_remark': '功能演示测试数据'})
                    if scenario != 'Q':
                        insert(c, 'finished_goods_data', {'流水号': sn, '批次号': batch, '机型': m, '状态': fg_status,
                               '预计入库时间': due, '更新时间': now, '占用订单号': order if allocated else None,
                               '客户': customer if allocated else '', '代理商': dealer if allocated else '',
                               '合同号': contract if allocated else '', '合同备注': '功能演示测试数据',
                               'Location_Code': slot if scenario == 'C' and not shipped else ''})
                    if scenario == 'P':
                        insert(c, 'plan_import', {'流水号': sn, '批次号': batch, '机型': m, '状态': '待入库', '预计入库时间': due,
                               '客户': customer if allocated else '', '代理商': dealer if allocated else '', '合同号': contract if allocated else '', '订单号': order if allocated else ''})
                    if scenario != 'Q':
                        insert(c, 'production_history_ledger', {'unit_id': sn, 'production_line_id': line, 'production_line_name': f'演示产线{i:02}',
                               'batch_code': batch, 'model_type': m, 'status': batch_status, 'scheduled_at': now-timedelta(days=14),
                               'completed_at': now-timedelta(days=7) if scenario == 'C' else None})
                    if scenario == 'C':
                        inbound = now-timedelta(days=7)
                        insert(c, 'inbound_history', {'serial_no': sn, 'inbound_time': inbound, 'source': 'demo', 'slot_code': slot,
                               'operator': 'demo_admin', 'batch_no': batch, 'model': m, 'status_before': '待入库', 'status_after': '库存中'})
                        insert(c, 'transaction_log', {'时间': inbound, '操作类型': '入库', '流水号': sn, '操作员': 'demo_admin'})
                    if allocated or scenario == 'Q' and j == 1:
                        insert(c, 'sales_orders', {'订单号': order, '客户名': customer, '代理商': dealer, '需求机型': f'{m}:1', '需求数量': 1,
                               '下单时间': now-timedelta(days=10), '备注': '功能演示测试订单', '包装选项': '标准包装', '发货时间': due,
                               '指定批次/来源': '{}', 'status': 'shipped' if shipped else 'ready' if scenario == 'C' else 'active'})
                        insert(c, 'factory_plan', {'合同号': contract, '机型': m, '排产数量': '1', '要求交期': due.strftime('%Y-%m-%d'),
                               '状态': '已完工' if shipped else '待规划' if scenario == 'Q' else '已规划', '备注': '功能演示测试合同',
                               '订单号': order, '客户名': customer, '代理商': dealer, '指定批次/来源': '{}'})
                    if shipped:
                        insert(c, 'shipping_history', {'流水号': sn, '批次号': batch, '机型': m, '状态': '已出库', '更新时间': now-timedelta(days=2),
                               '占用订单号': order, '订单号': order, '客户': customer, '代理商': dealer, '合同号': contract, 'archive_month': now.strftime('%Y-%m')})
                        insert(c, 'transaction_log', {'时间': now-timedelta(days=2), '操作类型': '发货', '流水号': sn, '操作员': 'demo_admin'})
                    insert(c, 'sys_operation_log', {'user_id': 'demo_admin', 'username': '测试管理员', 'operate_time': now,
                           'module': '功能演示', 'action_type': '创建', 'content': '生成虚构演示机台', 'serial_no': sn})
            insert(c, 'dealer_orders', {'order_no': f'DEMO-DEALER-{i:02}', 'dealer_id': f'DEMO-D-{i:02}', 'dealer_name': dealer,
                   'customer_name': customer, 'contact_name': '测试联系人', 'contact_phone': '00000000000', 'model': m,
                   'quantity': 1, 'status': 'pending', 'ERMQ': 0, 'factory_pending': 0, 'regional_review_status': 'approved', 'source': 'demo', 'remark': '虚构测试订单'})
        add_demo_details(c, enabled, now)
        summary = {t: c.execute(text(f'SELECT COUNT(*) FROM `{t}`')).scalar() for t in TABLES}
    return {'database': name, 'enabled_models': len(enabled), 'counts': summary}


def add_demo_details(c, models, now):
    """Synthetic photo/part, rush-order and forecast scenarios (fresh demo only)."""
    insert(c, 'photo_item_library', {'position_code': 'DEMO_PLATE', 'item_name': '测试整机铭牌',
           'item_category': '铭牌', 'shooting_requirement': '上传测试图片演示，勿上传真实资料', 'default_required': 1,
           'default_ocr_enabled': 0, 'sort_order': 1, 'enabled': 1})
    for i, model in enumerate(models, 1):
        m = model['model_name']
        insert(c, 'model_photo_config', {'model_id': model['id'], 'position_code': 'DEMO_PLATE',
               'required': 1, 'ocr_enabled': 0, 'sort_order': 1, 'enabled': 1, 'remark': '测试拍照配置'})
        sn = f'DEMO-{i:02}-C-001'
        insert(c, 'machine_photo_tasks', {'serial_no': sn, 'model_name': m, 'position_code': 'DEMO_PLATE',
               'item_name': '测试整机铭牌', 'required': 1, 'ocr_enabled': 0, 'status': 'pending', 'sort_order': 1, 'enabled': 1,
               'created_by': 'demo_admin'})
        task_id = c.execute(text('SELECT LAST_INSERT_ID()')).scalar()
        insert(c, 'machine_component_bindings', {'binding_key': f'DEMO-BIND-{i:02}', 'machine_no': sn,
               'machine_batch_no': f'DEMO-B-{i:02}-C', 'model_name': m, 'machine_status': '库存中',
               'material_code': f'DEMO-MAT-{i:02}', 'material_name': '测试控制器', 'material_type': '测试配件',
               'component_serial_no': f'DEMO-PART-{i:02}', 'position_code': 'DEMO_CONTROLLER', 'position_name': '测试控制器位置',
               'bound_at': now.date(), 'active': 1, 'source': 'demo', 'source_task_id': task_id, 'check_status': 'confirmed'})
        add_prediction(c, model, i, now)
        if i <= 5:
            insert(c, 'rush_order_queue', {'contract_no': f'DEMO-HT-{i:02}-Q-1', 'customer': f'测试客户{i:02}有限公司',
                   'dealer_name': f'测试代理商{i:02}', 'model_type': m, 'due_date': (now+timedelta(days=3)).date(),
                   'remark': '测试加急需求', 'source': 'manual', 'status': 'pending', 'created_by': 'demo_admin'})


def add_prediction(c, model, i, now):
    batch = f'DEMO-B-{i:02}-F'
    due = (now + timedelta(days=21)).date()
    insert(c, 'batches', {'batch_id': batch, 'batch_no': i*10+3, 'batch_code': batch,
           'model_type': model['model_name'], 'major_category': model['model_family'], 'capacity': 2,
           'base_capacity': 2, 'status': 'Predicted', 'source': 'forecast', 'due_date_start': due,
           'due_date_end': due, 'expected_inbound_date': due})
    for j in (1, 2):
        insert(c, 'units', {'unit_id': f'DEMO-{i:02}-F-{j:03}', 'forecast_serial_no': f'DEMO-FC-{i:02}-{j}',
               'batch_id': batch, 'slot_index': j, 'model_type': model['model_name'], 'status': 'Predicted',
               'due_date': due, 'order_remark': '虚构预测占位'})
    insert(c, 'forecast_batch_slots', {'slot_no': i, 'model_type': model['model_name'], 'capacity': 2,
           'batch_id': batch, 'source': 'forecast'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='v8_demo_showcase')
    args = parser.parse_args()
    print(json.dumps(create_demo(args.database), ensure_ascii=False, indent=2))
