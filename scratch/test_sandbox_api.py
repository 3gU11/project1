# -*- coding: utf-8 -*-
import requests
import json

print("=== Testing Go Sandbox Health Directly ===")
try:
    r = requests.get('http://127.0.0.1:3001/api/health', timeout=5)
    print("Go Direct Health Status:", r.status_code)
    print("Go Direct Health Response:", r.json())
except Exception as e:
    print("Go Direct Health failed:", e)

print("\n=== Logging into Python API to get Token ===")
try:
    login = requests.post('http://127.0.0.1:8000/api/v1/auth/login', data={'username': 'admin', 'password': '888'}, timeout=5)
    print("Login Status:", login.status_code)
    token = login.json().get('access_token')
    print("Login Token:", token[:25] + "..." if token else None)
except Exception as e:
    print("Login failed:", e)
    token = None

if token:
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print("\n=== Testing /api/v1/sandbox/production-lines via Proxy ===")
    try:
        # FastAPI prefix is /api/v1/sandbox. 
        # Sandbox route is /production-lines{path:path} which forwards to /api/production-lines{path}
        r = requests.get('http://127.0.0.1:8000/api/v1/sandbox/production-lines', headers=headers, timeout=5)
        print("Proxy lines Status:", r.status_code)
        data = r.json()
        print("Proxy lines type:", type(data))
        if isinstance(data, list):
            print("Proxy lines count:", len(data))
            if len(data) > 0:
                print("First line info:", data[0].get("line_id"), data[0].get("line_name"))
        else:
            print("Proxy lines response:", data)
    except Exception as e:
        print("Proxy lines failed:", e)
