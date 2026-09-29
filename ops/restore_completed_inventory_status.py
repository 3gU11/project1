"""Restore only the 21 reviewed statuses; never restore disputed bindings."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text, bindparam
from database import get_engine

SERIALS = [f'96-08-{n}' for n in [*range(31, 37), *range(46, 51), *range(271, 279), 297, 298]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    engine = get_engine()
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f'repair_restore_status_{run_id}_fg'
    query = text('''SELECT f.* FROM finished_goods_data f
        WHERE f.`流水号` IN :sns ORDER BY f.`流水号` FOR UPDATE''').bindparams(bindparam('sns', expanding=True))
    with engine.connect() as c:
        if args.apply:
            c.execute(text(f'CREATE TABLE {backup} LIKE finished_goods_data'))
            c.commit()
        with c.begin():
            rows = list(c.execute(query, {'sns': SERIALS}).mappings())
            if len(rows) != 21 or {r['流水号'] for r in rows} != set(SERIALS):
                raise RuntimeError('Expected exactly 21 unique inventory rows')
            for r in rows:
                if (r['状态'] != '待入库' or str(r['更新时间']) != '2026-09-18 09:50:21'
                        or r['占用订单号'] or r['合同号']):
                    raise RuntimeError(f'Changed record: {r["流水号"]}; aborting')
            evidence = c.execute(text('''SELECT COUNT(*) FROM units u
                JOIN repair_backup_unlogged_bindings_20260918_095021_fg b
                ON b.`流水号`=COALESCE(NULLIF(u.serial_no,''),u.forecast_serial_no)
                WHERE b.`流水号` IN :sns AND b.`状态`='待发货' AND u.status='Completed'
                AND EXISTS (SELECT 1 FROM inbound_history h WHERE h.serial_no=b.`流水号`)''')
                .bindparams(bindparam('sns', expanding=True)), {'sns': SERIALS}).scalar_one()
            if evidence != 21:
                raise RuntimeError('Backup/completion/inbound evidence mismatch')
            if args.apply:
                c.execute(text(f'INSERT INTO {backup} SELECT * FROM finished_goods_data WHERE `流水号` IN :sns')
                          .bindparams(bindparam('sns', expanding=True)), {'sns': SERIALS})
                result = c.execute(text("UPDATE finished_goods_data SET `状态`='待发货',`更新时间`=NOW() WHERE `流水号` IN :sns")
                                   .bindparams(bindparam('sns', expanding=True)), {'sns': SERIALS})
                if result.rowcount != 21:
                    raise RuntimeError('Unexpected update count')
                c.execute(text('''INSERT INTO sys_operation_log
                    (user_id,username,operate_time,module,action_type,biz_type,content,serial_no)
                    VALUES ('SystemRepair','SystemRepair',NOW(),'库存同步','数据纠错','机台',:content,:sn)'''),
                    [{'sn': sn, 'content': f'按用户确认恢复误重置的已完工机台库存状态：待入库→待发货；不恢复争议订单绑定；备份表：{backup}'} for sn in SERIALS])
    print(json.dumps({'applied': args.apply, 'count': 21, 'backup': backup if args.apply else None, 'serials': SERIALS}))


if __name__ == '__main__':
    main()
