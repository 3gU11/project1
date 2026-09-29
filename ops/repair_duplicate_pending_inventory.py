"""Back up and merge the four audited duplicate pending inventory records."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import bindparam, text
from database import get_engine, ensure_finished_goods_unique_serial

SERIALS = ['96-08-213', '96-08-214', '96-08-300', '96-08-301']
ORDER = 'SO-20260918-F36A'
CONTRACT = 'HT202608290003'


def main(apply=False):
    engine = get_engine()
    with engine.begin() as c:
        records = [dict(r) for r in c.execute(text(
            'SELECT * FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE'
        ).bindparams(bindparam('sns', expanding=True)), {'sns': SERIALS}).mappings()]
        for sn in SERIALS:
            group = [r for r in records if r['流水号'] == sn]
            assert len(group) == 2 and all(r['状态'] == '待入库' for r in group), sn
            blank = [r for r in group if not any(r[k] for k in ['占用订单号', '合同号', '客户', '代理商', '合同备注', 'Location_Code'])]
            bound = [r for r in group if r['占用订单号'] == ORDER and r['合同号'] == CONTRACT]
            assert len(blank) == len(bound) == 1, sn
            assert all(blank[0][k] == bound[0][k] for k in ['批次号', '机型', '预计入库时间']), sn
            unit = c.execute(text("SELECT contract_no,sales_id FROM units WHERE COALESCE(NULLIF(serial_no,''),forecast_serial_no)=:sn FOR UPDATE"), {'sn': sn}).one()
            assert tuple(unit) == (CONTRACT, ORDER), sn
            assert c.execute(text("SELECT COUNT(*) FROM sys_operation_log WHERE serial_no=:sn AND order_no=:order AND module='订单配货' AND action_type='配货'"), {'sn': sn, 'order': ORDER}).scalar(), sn
        if not apply:
            print(json.dumps({'candidates': SERIALS, 'remove': 4, 'retain_order': ORDER}))
            return
        path = Path(__file__).resolve().parents[1] / 'data_repair_backups' / ('duplicate-pending-' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
        with path.open('x', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, default=str, indent=2)
        deleted = c.execute(text("""DELETE FROM finished_goods_data
            WHERE `流水号` IN :sns AND `状态`='待入库'
              AND COALESCE(`占用订单号`,'')='' AND COALESCE(`合同号`,'')=''
              AND COALESCE(`客户`,'')='' AND COALESCE(`代理商`,'')=''
              AND COALESCE(`合同备注`,'')='' AND COALESCE(`Location_Code`,'')=''
        """).bindparams(bindparam('sns', expanding=True)), {'sns': SERIALS}).rowcount
        assert deleted == 4
        c.execute(text("INSERT INTO sys_operation_log (user_id,username,operate_time,module,action_type,biz_type,content) VALUES ('SystemRepair','SystemRepair',NOW(),'库存同步','重复流水号合并','机台',:content)"), {'content': f'保留人工配货记录 {ORDER}，清理4条空白重复记录；流水号：{SERIALS}；备份：{path}'})
    # MySQL DDL commits implicitly, so enforce uniqueness after the audited DML transaction.
    with engine.begin() as c:
        ensure_finished_goods_unique_serial(c)
    print(json.dumps({'deleted_duplicates': deleted, 'backup': str(path), 'unique_serial_enforced': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
