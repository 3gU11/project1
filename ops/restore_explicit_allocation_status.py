"""Repair the reviewed four-machine legacy allocation, without replaying inbound."""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import bindparam, text
from database import get_engine

SNS = ['96-08-213', '96-08-214', '96-08-300', '96-08-301']
ORDER = 'SO-20260918-F36A'


def main():
    with get_engine().begin() as c:
        order = dict(c.execute(text('SELECT * FROM sales_orders WHERE `订单号`=:o FOR UPDATE'), {'o': ORDER}).mappings().one())
        assert order['status'] == 'allocated' and int(order['需求数量']) == 4
        rows = [dict(r) for r in c.execute(text('SELECT * FROM finished_goods_data WHERE `占用订单号`=:o FOR UPDATE'), {'o': ORDER}).mappings()]
        assert len(rows) == 4 and {r['流水号'] for r in rows} == set(SNS)
        assert all(r['状态'] == '待入库' and r['合同号'] == 'HT202608290003' for r in rows)
        units = [dict(r) for r in c.execute(text('''SELECT * FROM units WHERE
            COALESCE(NULLIF(serial_no,''),forecast_serial_no) IN :sns FOR UPDATE''').bindparams(bindparam('sns', expanding=True)), {'sns': SNS}).mappings()]
        assert len(units) == 4 and all(u['status'] == 'In_Production' and u['sales_id'] == ORDER for u in units)
        for sn in SNS:
            assert c.execute(text("SELECT COUNT(*) FROM sys_operation_log WHERE serial_no=:s AND order_no=:o AND action_type='配货'"), {'s': sn, 'o': ORDER}).scalar()
            assert c.execute(text('SELECT COUNT(*) FROM inbound_history WHERE serial_no=:s'), {'s': sn}).scalar()
        backup = Path('data_repair_backups') / ('explicit-allocation-status-' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
        with backup.open('x', encoding='utf-8') as f:
            json.dump({'order': order, 'inventory': rows, 'units_readonly': units}, f, ensure_ascii=False, default=str, indent=2)
        n = c.execute(text("UPDATE finished_goods_data SET `状态`='待发货',`更新时间`=NOW() WHERE `占用订单号`=:o AND `状态`='待入库'"), {'o': ORDER}).rowcount
        assert n == 4
        assert c.execute(text("UPDATE sales_orders SET status='ready' WHERE `订单号`=:o AND status='allocated'"), {'o': ORDER}).rowcount == 1
        c.execute(text('''INSERT INTO sys_operation_log
            (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no)
            VALUES ('SystemRepair','SystemRepair',NOW(),'订单配货','数据纠错','机台',:content,:sn,:o)'''),
            [{'sn': sn, 'o': ORDER, 'content': f'按用户确认补正已有人工配货：待入库改为待发货；订单allocated改为ready；保留在产卡片及原入库历史，不新增入库事件；备份：{backup}'} for sn in SNS])
    print(json.dumps({'restored': n, 'order_status': 'ready', 'backup': str(backup)}))


if __name__ == '__main__':
    main()
