import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crud.inventory import merge_required_warehouse_slots, sanitize_warehouse_layout
from database import get_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐默认仓库布局中的必需库位")
    parser.add_argument("--layout-id", default="default")
    parser.add_argument("--apply", action="store_true", help="确认写入数据库；默认仅预检")
    args = parser.parse_args()

    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT layout_json, update_time FROM warehouse_layout WHERE layout_id=:layout_id"),
            {"layout_id": args.layout_id},
        ).fetchone()
    if row is None:
        raise RuntimeError(f"布局不存在: {args.layout_id}")

    original = json.loads(row[0] or "{}")
    original_slots = original.get("slots", []) if isinstance(original, dict) else []
    merged = sanitize_warehouse_layout(original)
    merged["slots"] = merge_required_warehouse_slots(original_slots)
    added = len(merged["slots"]) - len(original_slots)
    print(f"layout={args.layout_id} current={len(original_slots)} added={added} final={len(merged['slots'])}")
    if not args.apply or added == 0:
        print("dry-run" if not args.apply else "no changes")
        return 0

    backup_dir = Path(__file__).resolve().parents[1] / "artifacts" / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"warehouse_layout_{args.layout_id}_{timestamp}.json"
    backup_path.write_text(
        json.dumps({"layout_id": args.layout_id, "update_time": str(row[1] or ""), "layout_json": original}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload = json.dumps(merged, ensure_ascii=False)
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE warehouse_layout SET layout_json=:layout_json, update_time=NOW() "
                "WHERE layout_id=:layout_id"
            ),
            {"layout_id": args.layout_id, "layout_json": payload},
        )
    print(f"applied backup={backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
