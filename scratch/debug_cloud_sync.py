import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from crud.cloud_dealer_order_sync import sync_wechat_batch_summary_to_cloud
import json

try:
    print("Attempting to sync wechat batch summary to cloud...")
    result = sync_wechat_batch_summary_to_cloud()
    print("Sync Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
except Exception as e:
    import traceback
    print("Sync failed with error:")
    traceback.print_exc()
