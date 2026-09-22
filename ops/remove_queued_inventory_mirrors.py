"""Remove only the two user-approved, unallocated queued inventory mirrors."""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text, bindparam
from database import get_engine


def main():
    sns = ['96-09-216', '96-09-218']
    with get_engine().begin() as c:
        q = text('SELECT * FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE').bindparams(bindparam('sns', expanding=True))
        records = [dict(r) for r in c.execute(q, {'sns': sns}).mappings()]
        assert len(records) == 2 and {r['流水号'] for r in records} == set(sns)
        for r in records:
            assert r['状态'] == '待入库' and not r['占用订单号'] and not r['合同号'] and not r['Location_Code']
        units = [dict(r) for r in c.execute(text('''SELECT u.* FROM units u JOIN batches b ON b.batch_id=u.batch_id
            WHERE COALESCE(NULLIF(u.serial_no,''),u.forecast_serial_no) IN :sns
              AND b.status='Confirmed' AND u.status='Pending' FOR UPDATE''').bindparams(bindparam('sns', expanding=True)), {'sns': sns}).mappings()]
        assert len(units) == 2 and all(not u['sales_id'] and not u['production_line_id'] for u in units)
        for r in records:
            unit = next(u for u in units if (u['serial_no'] or u['forecast_serial_no']) == r['流水号'])
            assert (r['合同备注'] or '') == (unit['order_remark'] or ''), 'Preserve remarks on queued card'
        backup = Path('data_repair_backups') / ('remove-queued-mirrors-' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
        with backup.open('x', encoding='utf-8') as f:
            json.dump({'inventory': records, 'units_readonly': units}, f, ensure_ascii=False, default=str, indent=2)
        deleted = c.execute(text('DELETE FROM finished_goods_data WHERE `流水号` IN :sns').bindparams(bindparam('sns', expanding=True)), {'sns': sns}).rowcount
        assert deleted == 2
        c.execute(text('''INSERT INTO sys_operation_log (user_id,username,operate_time,module,action_type,biz_type,content)
            VALUES ('SystemRepair','SystemRepair',NOW(),'库存同步','移除待排产库存镜像','机台',:content)'''),
            {'content': f'按用户要求移除96-09-216、96-09-218的待排产库存记录；保留排产卡片及历史日志；备份：{backup}'})
    print(json.dumps({'deleted': deleted, 'backup': str(backup)}))


if __name__ == '__main__':
    main()
