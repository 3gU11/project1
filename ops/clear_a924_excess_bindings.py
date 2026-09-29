"""Clear the three user-confirmed excess bindings, preserving production/configuration."""
import json
import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text, bindparam
from database import get_engine

SNS = ['96-09-181', '96-09-182', '96-09-183']
ORDER = 'SO-20260917-A924'


def main():
    with get_engine().begin() as c:
        def rows(sql):
            return [dict(r) for r in c.execute(text(sql).bindparams(bindparam('sns', expanding=True)), {'sns': SNS}).mappings()]
        units = rows("SELECT * FROM units WHERE COALESCE(NULLIF(serial_no,''),forecast_serial_no) IN :sns FOR UPDATE")
        fg = rows('SELECT * FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE')
        assert len(units) == len(fg) == 3
        assert all(u['sales_id'] == ORDER and u['contract_no'] == 'HT202609170005' and u['status'] == 'In_Production' and u['production_line_id'] == 'line-13' and not u['is_locked'] for u in units)
        assert all(r['占用订单号'] == ORDER and r['合同号'] == 'HT202609170005' and r['状态'] == '待入库' for r in fg)
        valid = [dict(r) for r in c.execute(text('SELECT * FROM finished_goods_data WHERE `占用订单号`=:o AND `状态`=\'待发货\' FOR UPDATE'), {'o': ORDER}).mappings()]
        assert {r['流水号'] for r in valid} == {'96-08-10', '96-08-11', '96-08-120'}
        path = Path('data_repair_backups') / ('clear-a924-' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
        with path.open('x', encoding='utf-8') as f:
            json.dump({'units': units, 'inventory': fg, 'retained_allocations': valid}, f, ensure_ascii=False, default=str, indent=2)
        for sql in ["UPDATE units SET sales_id=NULL,contract_no=NULL,customer=NULL,dealer_id=NULL,dealer_name=NULL,due_date=NULL,is_contract_pinned=0,updated_at=NOW() WHERE COALESCE(NULLIF(serial_no,''),forecast_serial_no) IN :sns", "UPDATE finished_goods_data SET `占用订单号`=NULL,`合同号`='',`客户`='',`代理商`='',`更新时间`=NOW() WHERE `流水号` IN :sns"]:
            assert c.execute(text(sql).bindparams(bindparam('sns', expanding=True)), {'sns': SNS}).rowcount == 3
        c.execute(text('''INSERT INTO sys_operation_log (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
            VALUES ('SystemRepair','SystemRepair',NOW(),'订单配货','数据纠错','机台',:content,:sn,:o,'HT202609170005')'''),
            [{'sn': sn, 'o': ORDER, 'content': f'按用户确认解除超量残留绑定，同步清除看板和库存订单合同信息；保留13号线在产状态及不配水箱配置；备份：{path}'} for sn in SNS])
    print(json.dumps({'cleared': SNS, 'backup': str(path)}))


if __name__ == '__main__':
    main()
