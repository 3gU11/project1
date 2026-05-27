# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
import httpx
from crud.cloud_dealer_order_sync import _cloud_config, _get_http_client, fetch_cloud_dealer_orders

base_url, api_key = _cloud_config()
print(f"Cloud Config Base URL: {base_url}")
print(f"Cloud Config API Key: {api_key[:10]}... (length: {len(api_key)})")

headers = {"X-V7-API-KEY": api_key}

with httpx.Client(timeout=10.0, trust_env=False) as client:
    # 1. Test Base URL/Ping or simple get
    print("\n--- Testing GET /api/v7/dealer-orders (Pending) ---")
    try:
        r = client.get(f"{base_url}/api/v7/dealer-orders", params={"status": "pending", "page": 1, "page_size": 2}, headers=headers)
        print(f"Status Code: {r.status_code}")
        print("Response Headers:", dict(r.headers))
        try:
            data = r.json()
            print("Response JSON keys:", data.keys() if isinstance(data, dict) else type(data))
            if isinstance(data, dict) and "data" in data:
                print(f"Number of orders returned: {len(data['data'])}")
                if len(data['data']) > 0:
                    print("Sample Order:", data['data'][0].get("order_no") or data['data'][0].get("orderNo"))
        except ValueError:
            print("Response Text:", r.text[:200])
    except Exception as e:
        print("Error:", e)

    # 2. Test Sync endpoint (wechat-batch-summary/sync)
    print("\n--- Testing POST /api/v7/wechat-batch-summary/sync (Dry-run or empty sync) ---")
    try:
        r = client.post(
            f"{base_url}/api/v7/wechat-batch-summary/sync",
            headers={"X-V7-API-KEY": api_key, "Idempotency-Key": "test-connectivity-key"},
            json={"mode": "replace", "rows": []}
        )
        print(f"Status Code: {r.status_code}")
        print("Response Text:", r.text)
    except Exception as e:
        print("Error:", e)

    # 3. Test Order Status Endpoint (dummy order)
    print("\n--- Testing POST /api/dealer/orders/DUMMY-ORDER-NO/v8-status ---")
    try:
        r = client.post(
            f"{base_url}/api/dealer/orders/DUMMY-ORDER-NO/v8-status",
            headers={"X-V7-API-KEY": api_key, "Idempotency-Key": "test-connectivity-key"},
            json={
                "status": "approved",
                "reviewedBy": "system-test",
                "reviewNote": "connectivity test",
                "updatedAt": "2026-05-25 12:00:00"
            }
        )
        print(f"Status Code: {r.status_code}")
        print("Response Text:", r.text)
    except Exception as e:
        print("Error:", e)
