"""Restore the user-confirmed accidental completion of batch 08-15."""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from database import get_engine

BATCH = 'BATCH-202608-XS-007-45078502'

def main():
    with get_engine().begin() as c:
        def rows(sql):
            return [dict(r) for r in c.execute(text(sql), {'b': BATCH}).mappings()]
        batch = rows('SELECT * FROM batches WHERE batch_id=:b FOR UPDATE')
        line = rows("SELECT * FROM production_lines WHERE line_id='line-05' FOR UPDATE")
        units = rows('SELECT * FROM units WHERE batch_id=:b FOR UPDATE')
        ledger = rows('SELECT * FROM production_history_ledger WHERE unit_id IN (SELECT unit_id FROM units WHERE batch_id=:b) FOR UPDATE')
        assert len(batch) == 1 and batch[0]['status'] == 'Completed'
        assert len(line) == 1 and line[0]['status'] == 'Idle' and not line[0]['current_batch_id']
        assert len(units) == 30 and all(u['status'] == 'Completed' and not u['production_line_id'] for u in units)
        assert len(ledger) == 30 and len({r['unit_id'] for r in ledger}) == 30
        assert all(r['status'] == 'Completed' and r['batch_code'] == '08-15' for r in ledger)
        assert not rows("SELECT unit_id FROM units WHERE production_line_id='line-05' FOR UPDATE")
        assert not rows("SELECT batch_id FROM batches WHERE production_line_id='line-05' AND status='In_Production' FOR UPDATE")
        inventory = rows('SELECT fg.* FROM finished_goods_data fg JOIN units u ON fg.`流水号`=COALESCE(u.serial_no,u.forecast_serial_no) COLLATE utf8mb4_general_ci WHERE u.batch_id=:b')
        assert len(inventory) == 30 and all(r['状态'] == '待入库' for r in inventory)
        backup = Path(__file__).resolve().parents[1] / 'data_repair_backups' / ('restore-0815-line05-' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
        backup.parent.mkdir(exist_ok=True)
        with backup.open('x', encoding='utf-8') as f:
            json.dump({'reason': 'User confirmed accidental completion and actual line 05', 'batch': batch, 'line': line, 'units': units, 'ledger': ledger, 'inventory_readonly': inventory}, f, ensure_ascii=False, default=str, indent=2)
        changes = {}
        changes['batch'] = c.execute(text("UPDATE batches SET status='In_Production',production_line_id='line-05',updated_at=NOW() WHERE batch_id=:b"), {'b': BATCH}).rowcount
        changes['units'] = c.execute(text("UPDATE units SET status='In_Production',production_line_id='line-05',updated_at=NOW() WHERE batch_id=:b"), {'b': BATCH}).rowcount
        changes['ledger'] = c.execute(text("UPDATE production_history_ledger SET status='In_Production',production_line_id='line-05',production_line_name=:name,completed_at=NULL,updated_at=NOW() WHERE unit_id IN (SELECT unit_id FROM units WHERE batch_id=:b)"), {'b': BATCH, 'name': line[0]['line_name']}).rowcount
        changes['line'] = c.execute(text("UPDATE production_lines SET status='Busy',current_batch_id=:b,updated_at=NOW() WHERE line_id='line-05'"), {'b': BATCH}).rowcount
        assert changes == {'batch': 1, 'units': 30, 'ledger': 30, 'line': 1}
        c.execute(text("INSERT INTO sys_operation_log (user_id,username,operate_time,module,action_type,biz_type,content) VALUES ('SystemRepair','SystemRepair',NOW(),'生产看板','误完工恢复','批次',:content)"), {'content': '按用户确认将08-15批次及30台恢复到5号线生产中，清除错误完工时间；备份：' + str(backup)})
    print(json.dumps({'committed': True, 'changes': changes, 'backup': str(backup)}, ensure_ascii=True))

if __name__ == '__main__':
    main()
