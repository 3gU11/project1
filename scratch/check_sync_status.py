import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from crud.cloud_sync_outbox import get_cloud_sync_status
import json
print(json.dumps(get_cloud_sync_status(10), indent=2, ensure_ascii=False))
