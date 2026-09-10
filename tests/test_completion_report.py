"""Exercise the report query against isolated event and machine fixtures."""
import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from crud import reports


@pytest.fixture
def report_db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.create_collation('utf8mb4_0900_ai_ci', lambda a, b: (a > b) - (a < b))
    conn.create_function('DATE_FORMAT', 2, lambda value, fmt:
                         datetime.fromisoformat(value).strftime(fmt.replace('%i', '%M').replace('%s', '%S'))
                         if value else None)
    columns = '''流水号 TEXT, 批次号 TEXT, 机型 TEXT, 状态 TEXT,
        预计入库时间 TEXT, 更新时间 TEXT, 占用订单号 TEXT, 客户 TEXT,
        代理商 TEXT, 合同号 TEXT, 合同备注 TEXT, Location_Code TEXT'''
    for table in ('finished_goods_data', 'shipping_history'):
        conn.execute(f'CREATE TABLE {table} ({columns})')
    conn.executescript('''
        CREATE TABLE sys_operation_log (serial_no TEXT, operate_time TEXT,
            module TEXT, action_type TEXT, biz_type TEXT);
        CREATE TABLE transaction_log (流水号 TEXT, 时间 TEXT, 操作类型 TEXT);
        CREATE TABLE model_dictionary (model_name TEXT, sort_order INTEGER);
        INSERT INTO model_dictionary VALUES ('M1', 1), ('M2', 2);
    ''')
    read_sql = pd.read_sql

    def compatible_read(sql, db, **kwargs):
        # SQLite runs the production CTE/window logic; adapt only date arithmetic.
        sql = str(sql).replace('DATE_ADD(:end_date, INTERVAL 1 DAY)',
                               "datetime(:end_date, '+1 day')")
        return read_sql(sql, db, **kwargs)

    monkeypatch.setattr(reports, 'get_engine', lambda: SimpleNamespace(connect=lambda: conn))
    monkeypatch.setattr(reports.pd, 'read_sql', compatible_read)

    def machine(sn, status='库存中', model='M1', customer='C1', table='finished_goods_data'):
        conn.execute(f'INSERT INTO {table} (流水号, 机型, 状态, 客户) VALUES (?, ?, ?, ?)',
                     (sn, model, status, customer))

    def event(sn, when, auto=False, operation=None):
        if auto:
            conn.execute('INSERT INTO transaction_log VALUES (?, ?, ?)',
                         (sn, when, operation or '直接配货-自动入库'))
        else:
            conn.execute('INSERT INTO sys_operation_log VALUES (?, ?, ?, ?, ?)',
                         (sn, when, '入库作业', operation or '入库', '机台'))

    yield machine, event
    conn.close()


def test_first_event_before_period_filter_and_current_status_before_archive(report_db):
    machine, event = report_db
    for sn in ('manual', 'automatic', 'old', 'future', 'withdrawn', 'no-event', 'transfer', 'blank'):
        machine(sn, status='待入库' if sn == 'withdrawn' else ('' if sn == 'blank' else '库存中'))
    machine('withdrawn', status='已出库', table='shipping_history')
    machine('archived', status='已出库', table='shipping_history')
    event('manual', '2026-05-01 00:00:00')
    event('manual', '2026-06-01 12:00:00', auto=True)
    event('automatic', '2026-08-31 23:59:59', auto=True)
    event('automatic', '2026-08-31 23:59:59', auto=True, operation='配货自动入库')
    event('old', '2026-04-30 23:59:59', auto=True)
    event('old', '2026-05-02 12:00:00')
    event('future', '2026-09-01 00:00:00')
    event('withdrawn', '2026-06-01 12:00:00', auto=True)
    event('blank', '2026-06-01 12:00:00')
    event('transfer', '2026-06-01 12:00:00', operation='调拨')
    event('archived', '2026-07-01 12:00:00')

    summary, detail = reports.get_completion_output_report_data('2026-05-01', '2026-08-31')
    assert set(detail['流水号']) == {'manual', 'automatic', 'archived'}
    assert summary['数量'].sum() == len(detail) == 3
    assert detail.set_index('流水号').loc['automatic', '入库方式'] == '自动匹配入库'


def test_filters_and_empty_results_keep_detail_and_summary_consistent(report_db):
    machine, event = report_db
    for sn, model, customer in [('a', 'M1', 'C1'), ('b', 'M2', 'C1'), ('c', 'M1', 'C2')]:
        machine(sn, model=model, customer=customer)
        event(sn, '2026-07-01 12:00:00')
    summary, detail = reports.get_completion_output_report_data('2026-05-01', '2026-08-31', 'M1', 'C1')
    assert detail['流水号'].tolist() == ['a']
    assert summary[['机型', '数量', '占比']].to_dict('records') == [
        {'机型': 'M1', '数量': 1, '占比': '100.00%'}]
    summary, detail = reports.get_completion_output_report_data('2026-05-01', '2026-08-31', 'missing')
    assert summary.empty and detail.empty
