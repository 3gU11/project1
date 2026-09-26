"""Persist one two-stage notification per contract."""

import json
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import bindparam, text


def _snapshot(rows):
    rows = list(rows)
    first = rows[0] if rows else {}
    models = defaultdict(int)
    due_dates = set()
    for row in rows:
        model = str(row.get("机型") or "").strip()
        if model:
            models[model] += int(row.get("排产数量") or 0)
        due = row.get("要求交期")
        if isinstance(due, (datetime, date)):
            due = due.isoformat()[:10]
        if str(due or "").strip():
            due_dates.add(str(due).strip())
    return {
        "customer": str(first.get("客户名") or ""),
        "dealer": str(first.get("代理商") or ""),
        "due_date": "、".join(sorted(due_dates)),
        "models": [{"model": model, "quantity": qty} for model, qty in sorted(models.items())],
        "total": sum(models.values()),
    }


def contract_rows(conn, contract_ids):
    if not contract_ids:
        return {}
    rows = conn.execute(text(
        "SELECT `合同号`, `客户名`, `代理商`, `机型`, `排产数量`, `要求交期` "
        "FROM factory_plan WHERE `合同号` IN :ids ORDER BY id"
    ).bindparams(bindparam("ids", expanding=True)), {"ids": contract_ids}).mappings()
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row["合同号"])].append(dict(row))
    return grouped


def record_created(conn, grouped, operator):
    for contract_id, rows in grouped.items():
        snapshot = json.dumps(_snapshot(rows), ensure_ascii=False)
        insert = "INSERT OR IGNORE" if conn.dialect.name == "sqlite" else "INSERT IGNORE"
        conn.execute(text(f"""
            {insert} INTO contract_notifications
                (contract_id, created_snapshot, created_by, created_at, latest_at, version)
            VALUES (:cid, :snapshot, :operator, :now, :now, 1)
        """), {"cid": contract_id, "snapshot": snapshot, "operator": operator, "now": datetime.now()})


def record_converted(conn, grouped, order_id, operator):
    for contract_id, rows in grouped.items():
        snapshot = json.dumps(_snapshot(rows), ensure_ascii=False)
        now = datetime.now()
        exists = conn.execute(text("SELECT order_id FROM contract_notifications WHERE contract_id=:cid"),
                              {"cid": contract_id}).first()
        params = {"cid": contract_id, "snapshot": snapshot, "operator": operator, "oid": order_id, "now": now}
        if exists is None:
            conn.execute(text("""
                INSERT INTO contract_notifications
                    (contract_id, converted_snapshot, converted_by, converted_at, order_id, latest_at, version)
                VALUES (:cid, :snapshot, :operator, :now, :oid, :now, 1)
            """), params)
        elif not exists.order_id:
            conn.execute(text("""
                UPDATE contract_notifications
                SET converted_snapshot=:snapshot, converted_by=:operator, converted_at=:now,
                    order_id=:oid, latest_at=:now, version=version+1
                WHERE contract_id=:cid AND order_id IS NULL
            """), params)


def record_planned(conn, grouped, operator):
    for contract_id, rows in grouped.items():
        snapshot = json.dumps(_snapshot(rows), ensure_ascii=False)
        now = datetime.now()
        exists = conn.execute(text("SELECT version FROM contract_notifications WHERE contract_id=:cid"), {"cid": contract_id}).first()
        params = {"cid": contract_id, "snapshot": snapshot, "operator": operator, "now": now}
        if exists is None:
            conn.execute(text("""
                INSERT INTO contract_notifications (contract_id, planned_snapshot, planned_by, planned_at, latest_at, version)
                VALUES (:cid, :snapshot, :operator, :now, :now, 1)
            """), params)
        else:
            conn.execute(text("""
                UPDATE contract_notifications
                SET planned_snapshot=:snapshot, planned_by=:operator, planned_at=:now,
                    latest_at=:now, version=version+1
                WHERE contract_id=:cid AND planned_at IS NULL
            """), params)
