# -*- coding: utf-8 -*-
"""打印云端订单原始报文里到底有哪些字段，用来核对「小程序填了、V8 却不显示」。

用法：
    python tools/inspect_order_payload.py                 # 最近一份合同草稿
    python tools/inspect_order_payload.py DO1792742396299963DD7
    python tools/inspect_order_payload.py --file order.json

输出三块：
1. 原始报文的键与值（含 items 内的键）
2. 表单字段最终取到的值（空的会标出来）
3. 报文里有、但当前别名表没消费的键 —— 这类通常是"小程序有、V8 没接"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from crud.local_contract_drafts import (  # noqa: E402
    FIELD_ALIASES, ITEM_ALIASES, map_order_to_contract,
)
from database import get_engine  # noqa: E402

CONSUMED = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
CONSUMED |= {alias for aliases in ITEM_ALIASES.values() for alias in aliases}
CONSUMED |= {"items", "orderNo", "order_no", "id", "regionalManagerName", "regional_manager_name"}


def load_snapshot(order_no: str | None) -> tuple[str, dict]:
    with get_engine().connect() as conn:
        if order_no:
            row = conn.execute(text(
                "SELECT source_order_no, source_snapshot FROM v8_contract_drafts "
                "WHERE source_order_no=:no ORDER BY created_at DESC LIMIT 1"), {"no": order_no}).mappings().first()
        else:
            row = conn.execute(text(
                "SELECT source_order_no, source_snapshot FROM v8_contract_drafts "
                "ORDER BY created_at DESC LIMIT 1")).mappings().first()
    if not row:
        raise SystemExit("没有找到合同草稿。先在 V8 里同步一笔小程序订单，或把报文存成 JSON 用 --file 传进来。")
    return row["source_order_no"], json.loads(row["source_snapshot"] or "{}")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    if "--file" in args:
        path = Path(args[args.index("--file") + 1])
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        order_no = str(snapshot.get("orderNo") or snapshot.get("order_no") or path.name)
    else:
        order_no, snapshot = load_snapshot(args[0] if args else None)

    print(f"订单：{order_no}\n")

    print("=== 1. 原始报文 ===")
    for key, value in snapshot.items():
        if key == "items":
            continue
        print(f"  {key:26} = {value!r}")
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    for index, item in enumerate(items, 1):
        print(f"  items[{index}]:")
        for key, value in item.items():
            print(f"      {key:22} = {value!r}")

    print("\n=== 2. 表单字段取到的值 ===")
    fields = map_order_to_contract(snapshot)
    empty = []
    for key, value in fields.items():
        if value:
            print(f"  {key:26} = {value!r}")
        else:
            empty.append(key)
    if empty:
        print(f"  （空：{'、'.join(empty)}）")

    print("\n=== 3. 报文里有、但没有被字段映射消费的键 ===")
    unused = [key for key in snapshot if key not in CONSUMED]
    item_keys = {key for item in items if isinstance(item, dict) for key in item}
    unused_items = sorted(item_keys - CONSUMED)
    if unused:
        for key in unused:
            print(f"  {key:26} = {snapshot[key]!r}")
    if unused_items:
        print(f"  items 内的未消费键：{'、'.join(unused_items)}")
    if not unused and not unused_items:
        print("  （无，报文里的键都已映射）")


if __name__ == "__main__":
    main()
