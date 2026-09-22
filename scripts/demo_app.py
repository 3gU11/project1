"""ASGI entry point with demo-only file storage and no outbound integrations."""
import os
from pathlib import Path
import config

if not config.MYSQL_DB.startswith('v8_demo_'):
    raise RuntimeError('The demo API must use a v8_demo_* database')
runtime = Path(os.environ['V8_DEMO_RUNTIME']).resolve()
config.BASE_DIR = str(runtime)
config.CONTRACT_ABS_DIR = str(runtime / 'data' / 'contracts')
config.MACHINE_ARCHIVE_ABS_DIR = str(runtime / 'machine_archives')
from api.main import app


@app.middleware('http')
async def demo_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-V8-Demo'] = 'synthetic-data'
    return response
