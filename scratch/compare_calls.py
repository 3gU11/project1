import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
import requests
import traceback

login = requests.post('http://localhost:8000/api/v1/auth/login', data={'username': 'admin', 'password': '888'})
token = login.json().get('access_token')
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

# Now look at what the route handler's traceback says
# We need to directly call the function with the same context as the API would
from crud.dealer_orders import reject_dealer_order_extra_review

print("\n=== Testing direct call ===")
try:
    result = reject_dealer_order_extra_review(
        'DO202605220150464009',
        reviewer='admin',
        reason='test direct from context'
    )
    print("Direct call success:", result.get('status'))
except Exception as e:
    traceback.print_exc()

print("\n=== HTTP call ===")
r2 = requests.post(
    'http://localhost:8000/api/v1/dealer-orders/DO202605220150464009/extra-review/reject',
    json={'reason': 'test from http'},
    headers=headers
)
print('Status:', r2.status_code)
print('Response:', r2.text[:500])
