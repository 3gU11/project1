import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
import requests

login = requests.post('http://localhost:8000/api/v1/auth/login', data={'username': 'admin', 'password': '888'})
token = login.json().get('access_token')
print('Login token:', token[:30] + '...' if token else None)

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# First restore
from database import get_engine
from sqlalchemy import text
with get_engine().begin() as conn:
    conn.execute(
        text("UPDATE dealer_orders SET status='contracted', factory_pending=1 WHERE order_no='DO202605220150464009'"),
    )
    r = conn.execute(text("SELECT status, factory_pending FROM dealer_orders WHERE order_no='DO202605220150464009'")).fetchone()
    print(f"DB state: status={r[0]}, factory_pending={r[1]}")

# Now HTTP request
r = requests.post(
    'http://localhost:8000/api/v1/dealer-orders/DO202605220150464009/extra-review/reject',
    json={'reason': 'test from http'},
    headers=headers
)
print('Status:', r.status_code)
print('Response:', r.text[:1000])
