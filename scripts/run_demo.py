"""Run isolated demo services on 3100/3101/8100. Ctrl+C stops this demo only."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from demo_database import create_demo, validate_target
from database import get_engine
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='v8_demo_showcase')
    parser.add_argument('--lan', action='store_true', help='Expose the demo web entry on the LAN')
    args = parser.parse_args()
    web_host = '0.0.0.0' if args.lan else '127.0.0.1'
    source = get_engine()
    validate_target(args.database, source.url.database)
    for port in (3100, 3101, 8100):
        with socket.socket() as s:
            s.bind((web_host if port == 3100 else '127.0.0.1', port))
    with source.connect() as c:
        exists = c.execute(text('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=:n'), {'n': args.database}).scalar()
    if not exists:
        print(json.dumps(create_demo(args.database), ensure_ascii=False))
    from sqlalchemy import create_engine
    with create_engine(source.url.set(database=args.database)).connect() as c:
        marker = c.execute(text("SELECT config_value FROM system_config WHERE config_key='demo_database'")).scalar()
        if marker != 'synthetic-v1':
            raise RuntimeError('Database is not marked as a synthetic demo')
    runtime = ROOT / 'output' / args.database
    runtime.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        'PYTHONPATH': str(ROOT), 'PYTHONIOENCODING': 'utf-8', 'PYTHON_DOTENV_DISABLED': '1',
        'MYSQL_HOST': source.url.host, 'MYSQL_PORT': str(source.url.port or 3306),
        'MYSQL_USER': source.url.username, 'MYSQL_PASSWORD': source.url.password or '', 'MYSQL_DB': args.database,
        'DB_DSN': f'{source.url.username}:{source.url.password}@tcp({source.url.host}:{source.url.port or 3306})/{args.database}?charset=utf8mb4&parseTime=True&loc=Local',
        'V8_DEMO_MODE': '1', 'V8_DEMO_RUNTIME': str(runtime), 'HTTP_ADDR': '127.0.0.1:3101',
        'GO_SANDBOX_URL': 'http://127.0.0.1:3101', 'PYTHON_URL': 'http://127.0.0.1:8100',
        'GO_INTERNAL_TOKEN': 'isolated-demo-internal', 'REDIS_ENABLED': 'false', 'OCR_ENABLED': 'false',
        'ENABLE_CLOUD_PULL': 'false', 'REPAIR_SYNC_ENABLED': 'false', 'REPAIR_SYNC_REALTIME_ENABLED': 'false',
        'REPAIR_IDENTITY_API_KEY': '', 'REPAIR_SYNC_BASE_URL': 'http://127.0.0.1:9',
        'WECHAT_CLOUD_API_BASE': 'http://127.0.0.1:9', 'V7_API_KEY': 'demo-disabled',
        'V8_SYNC_SECRET': 'demo-disabled', 'CLOUD_SYNC_SECRET': 'demo-disabled',
        'VITE_PROXY_TARGET': 'http://127.0.0.1:8100', 'VITE_PHOTO_API_TARGET': 'http://127.0.0.1:3101',
        'VITE_API_BASE_URL': '/api/v1', 'ALLOW_ORIGINS': 'http://127.0.0.1:3100',
        'VITE_DEMO_MODE': 'true',
    })
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required')
    commands = [
        ('go', [str(ROOT/'server'/'smart-scheduling-server-go.exe')], runtime),
        ('api', [sys.executable, '-m', 'uvicorn', 'scripts.demo_app:app', '--host', '127.0.0.1', '--port', '8100'], runtime),
        ('web', [node, str(ROOT/'frontend'/'node_modules'/'vite'/'bin'/'vite.js'), '--host', web_host, '--port', '3100', '--strictPort'], ROOT/'frontend'),
    ]
    children, logs = [], []
    try:
        for name, command, cwd in commands:
            log = open(runtime/f'{name}.log', 'a', encoding='utf-8')
            logs.append(log)
            child = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            children.append(child)
        (runtime/'processes.json').write_text(json.dumps({'database': args.database, 'pids': [p.pid for p in children]}), encoding='utf-8')
        for _ in range(90):
            if any(p.poll() is not None for p in children):
                raise RuntimeError(f'Demo service stopped; inspect {runtime}')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8100/openapi.json', timeout=2) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('Demo API did not become ready')
        print('Demo: http://127.0.0.1:3100 | demo_admin / Demo123456', flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=15)
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
