import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from database import get_engine
from sqlalchemy import text

with get_engine().begin() as conn:
    # Get total count of events by status
    status_counts = conn.execute(
        text("SELECT status, COUNT(*) FROM cloud_sync_outbox GROUP BY status")
    ).fetchall()
    print("=== Sync Outbox Status Counts ===")
    for status, count in status_counts:
        print(f"Status: {status}, Count: {count}")

    # Get the latest 10 failed/pending events
    latest_events = conn.execute(
        text("SELECT id, event_id, event_type, biz_key, status, retry_count, last_error, updated_at FROM cloud_sync_outbox ORDER BY id DESC LIMIT 10")
    ).fetchall()
    print("\n=== Latest 10 Sync Outbox Events ===")
    for row in latest_events:
        print(dict(row._mapping))
