"""Compare a dump in an isolated MySQL instance with local inventory, read-only locally."""
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from sqlalchemy import text
from database import get_engine
from crud.inventory_scope import pending_inbound_scope_sql

def main():
    remote = pymysql.connect(host='127.0.0.1', port=23316, user='root', autocommit=True, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    with remote.cursor() as c:
        c.execute('SELECT @@datadir d')
        assert 'mysql-dump-validation' in c.fetchone()['d']
        c.execute('CREATE DATABASE IF NOT EXISTS compare_20260918_174751 CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
    with open('D:/IE下载/rjfinshed.sql', 'rb') as f:
        subprocess.run(['D:/JavaEnv/MySQL/mysql-8.0.45-winx64/bin/mysql.exe','--no-defaults','--host=127.0.0.1','--port=23316','--user=root','--default-character-set=utf8mb4','--max-allowed-packet=256M','compare_20260918_174751'],stdin=f,check=True,capture_output=True)
    remote.select_db('compare_20260918_174751')
    def canon(r):
        return json.dumps(r,sort_keys=True,ensure_ascii=True,default=str)
    with remote.cursor() as r, get_engine().connect() as local:
        r.execute('SELECT * FROM finished_goods_data')
        old=r.fetchall()
        new=[dict(x) for x in local.execute(text('SELECT * FROM finished_goods_data')).mappings()]
        groups=[]
        for rows in (old,new):
            d=defaultdict(list)
            for row in rows: d[row['流水号']].append(row)
            groups.append(d)
        diffs=[]
        for sn in sorted(set(groups[0])|set(groups[1])):
            a,b=groups[0][sn],groups[1][sn]
            if Counter(map(canon,a))!=Counter(map(canon,b)):
                diffs.append({'serial':sn,'dump':a,'local':b})
        counts=[]
        for rows in (old,new):
            pending=[x for x in rows if x['状态']=='待入库']
            counts.append({'rows':len(rows),'unique':len({x['流水号'] for x in rows}),'pending_rows':len(pending),'pending_unique':len({x['流水号'] for x in pending})})
        scope_sql=f"SELECT {pending_inbound_scope_sql()} scope,COUNT(*) n FROM finished_goods_data fg WHERE fg.`状态`='待入库' GROUP BY scope"
        r.execute(scope_sql)
        scopes={'dump':r.fetchall(),'local':[dict(x) for x in local.execute(text(scope_sql)).mappings()]}
        table_diffs=[]
        for t in ['units','batches','production_lines','production_history_ledger','orders','inbound_history','shipping_history']:
            r.execute('SHOW TABLES LIKE %s',(t,))
            if not r.fetchone(): continue
            r.execute('SELECT * FROM '+t)
            a=Counter(map(canon,r.fetchall()))
            b=Counter(canon(dict(x)) for x in local.execute(text('SELECT * FROM '+t)).mappings())
            table_diffs.append({'table':t,'dump_rows':sum(a.values()),'local_rows':sum(b.values()),'dump_only_versions':sum((a-b).values()),'local_only_versions':sum((b-a).values())})
        report={'counts':counts,'scopes':scopes,'inventory_differences':diffs,'tables':table_diffs}
        output=Path('data_repair_backups/compare-dump-174751.json')
        output.write_text(json.dumps(report,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
        print(json.dumps({'counts':counts,'scopes':scopes,'tables':table_diffs,'diffs':[{'sn':d['serial'],'dump_status':[x['状态'] for x in d['dump']],'local_status':[x['状态'] for x in d['local']],'changed_fields':sorted({k for a in d['dump'] for b in d['local'] for k in a if a[k]!=b[k]})} for d in diffs]},ensure_ascii=True,default=str))
    remote.close()

if __name__=='__main__': main()
