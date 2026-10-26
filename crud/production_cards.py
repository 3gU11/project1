"""Keep the production board aligned with machines that leave through shipping.

A machine can be reserved and shipped while its card is still on a production
line (在产预占直发). Shipping only updates ``finished_goods_data``, so without
this helper the card stays ``In_Production`` forever: the batch-level auto
completion in the Go service requires every unit of the batch to have an
inbound event, which a partially shipped batch never has.

The helpers below are intentionally column-tolerant: production deployments and
the isolated tests do not always expose the same columns, and a missing column
must never break the shipping transaction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Connection


def _table_columns(conn: Connection, table: str) -> set[str]:
    try:
        inspector = inspect(conn)
        if not inspector.has_table(table):
            return set()
        return {str(column.get("name") or "") for column in inspector.get_columns(table)}
    except Exception:
        return set()


def _serial_numbers(serial_nos: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in serial_nos or []:
        serial = str(value or "").strip()
        if not serial or serial in seen:
            continue
        seen.add(serial)
        result.append(serial)
    return result


def _match_sql(columns: set[str], alias: str = "") -> list[str]:
    prefix = f"{alias}." if alias else ""
    parts: list[str] = []
    if "serial_no" in columns:
        parts.append(f"TRIM(COALESCE({prefix}serial_no, '')) IN :sns")
    if "forecast_serial_no" in columns:
        parts.append(f"TRIM(COALESCE({prefix}forecast_serial_no, '')) IN :sns")
    return parts


def _recompute_line(
    conn: Connection,
    line_id: str,
    line_columns: set[str],
    batch_columns: set[str],
    now_text: str,
) -> None:
    if not {"line_id", "status"} <= line_columns:
        return
    if not {"batch_id", "status", "production_line_id"} <= batch_columns:
        return
    order_parts = ["batch_no ASC"] if "batch_no" in batch_columns else []
    order_parts.append("batch_id ASC")
    remaining = [
        str(row[0])
        for row in conn.execute(
            text(
                "SELECT batch_id FROM batches "
                "WHERE production_line_id=:line_id AND status='In_Production' "
                f"ORDER BY {', '.join(order_parts)}"
            ),
            {"line_id": line_id},
        ).fetchall()
        if str(row[0] or "").strip()
    ]
    current_row = conn.execute(
        text("SELECT current_batch_id, status FROM production_lines WHERE line_id=:line_id"),
        {"line_id": line_id},
    ).mappings().first()
    if not current_row:
        return
    if remaining:
        current_batch = str(current_row.get("current_batch_id") or "").strip()
        next_batch = current_batch if current_batch in remaining else remaining[0]
        set_parts = ["status='Busy'"]
        params: dict[str, Any] = {"line_id": line_id, "now_text": now_text}
        if "current_batch_id" in line_columns:
            set_parts.append("current_batch_id=:next_batch")
            params["next_batch"] = next_batch
        if "updated_at" in line_columns:
            set_parts.append("updated_at=:now_text")
        conn.execute(
            text(f"UPDATE production_lines SET {', '.join(set_parts)} WHERE line_id=:line_id"),
            params,
        )
        return
    set_parts = ["status='Idle'"]
    params = {"line_id": line_id, "now_text": now_text}
    if "current_batch_id" in line_columns:
        set_parts.append("current_batch_id=NULL")
    if "updated_at" in line_columns:
        set_parts.append("updated_at=:now_text")
    conn.execute(
        text(f"UPDATE production_lines SET {', '.join(set_parts)} WHERE line_id=:line_id"),
        params,
    )


def retire_shipped_production_cards(
    conn: Connection,
    serial_nos: Iterable[Any],
    now_text: str,
) -> dict[str, Any]:
    """Complete the production cards of shipped machines and free their slots.

    Only units still ``In_Production`` are touched. A batch is completed when it
    has no in-production unit left; the production line is recomputed from the
    batches that remain.
    """

    serials = _serial_numbers(serial_nos)
    result: dict[str, Any] = {"unit_ids": [], "completed_batches": [], "affected_lines": []}
    unit_columns = _table_columns(conn, "units")
    match_parts = _match_sql(unit_columns)
    if not serials or not match_parts or not {"unit_id", "status"} <= unit_columns:
        return result

    select_parts = ["unit_id", "status"]
    if "batch_id" in unit_columns:
        select_parts.append("batch_id")
    rows = conn.execute(
        text(
            f"SELECT {', '.join(select_parts)} FROM units "
            f"WHERE ({' OR '.join(match_parts)}) AND status='In_Production' FOR UPDATE"
        ).bindparams(bindparam("sns", expanding=True)),
        {"sns": serials},
    ).mappings().all()
    unit_ids = [str(row["unit_id"]) for row in rows if str(row.get("unit_id") or "").strip()]
    if not unit_ids:
        return result
    result["unit_ids"] = unit_ids

    unit_set = ["status='Completed'"]
    unit_params: dict[str, Any] = {"ids": unit_ids, "now_text": now_text}
    if "production_line_id" in unit_columns:
        unit_set.append("production_line_id=NULL")
    if "updated_at" in unit_columns:
        unit_set.append("updated_at=:now_text")
    conn.execute(
        text(
            f"UPDATE units SET {', '.join(unit_set)} "
            "WHERE unit_id IN :ids AND status='In_Production'"
        ).bindparams(bindparam("ids", expanding=True)),
        unit_params,
    )

    ledger_columns = _table_columns(conn, "production_history_ledger")
    if {"unit_id", "status"} <= ledger_columns:
        ledger_set = ["status='Completed'"]
        if "completed_at" in ledger_columns:
            ledger_set.append("completed_at=:now_text")
        if "updated_at" in ledger_columns:
            ledger_set.append("updated_at=:now_text")
        conn.execute(
            text(
                f"UPDATE production_history_ledger SET {', '.join(ledger_set)} "
                "WHERE unit_id IN :ids AND status='In_Production'"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": unit_ids, "now_text": now_text},
        )

    batch_ids = sorted(
        {
            str(row.get("batch_id") or "").strip()
            for row in rows
            if str(row.get("batch_id") or "").strip()
        }
    )
    batch_columns = _table_columns(conn, "batches")
    line_columns = _table_columns(conn, "production_lines")
    affected_lines: set[str] = set()
    for batch_id in batch_ids:
        line_id = ""
        if {"batch_id", "status"} <= batch_columns:
            select_parts = ["batch_id", "status"]
            if "production_line_id" in batch_columns:
                select_parts.append("production_line_id")
            batch_row = conn.execute(
                text(f"SELECT {', '.join(select_parts)} FROM batches WHERE batch_id=:batch_id"),
                {"batch_id": batch_id},
            ).mappings().first()
            if not batch_row:
                continue
            line_id = str(batch_row.get("production_line_id") or "").strip()
            if str(batch_row.get("status") or "").strip() == "In_Production":
                remaining = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM units "
                            "WHERE batch_id=:batch_id AND status='In_Production'"
                        ),
                        {"batch_id": batch_id},
                    ).scalar()
                    or 0
                )
                if remaining == 0:
                    batch_set = ["status='Completed'"]
                    if "updated_at" in batch_columns:
                        batch_set.append("updated_at=:now_text")
                    updated = conn.execute(
                        text(
                            f"UPDATE batches SET {', '.join(batch_set)} "
                            "WHERE batch_id=:batch_id AND status='In_Production'"
                        ),
                        {"batch_id": batch_id, "now_text": now_text},
                    ).rowcount
                    if updated:
                        result["completed_batches"].append(batch_id)
        if line_id:
            _recompute_line(conn, line_id, line_columns, batch_columns, now_text)
            affected_lines.add(line_id)

    result["affected_lines"] = sorted(affected_lines)
    return result


def restore_shipped_production_cards(
    conn: Connection,
    serial_nos: Iterable[Any],
    now_text: str,
) -> dict[str, Any]:
    """Put cards retired by :func:`retire_shipped_production_cards` back.

    Used by shipping withdrawal: the machines are still in production, only the
    shipment confirmation was reverted. Cards of machines whose batch or line is
    no longer active are left completed, matching the normal completion rules.
    """

    serials = _serial_numbers(serial_nos)
    result: dict[str, Any] = {"unit_ids": [], "affected_lines": []}
    unit_columns = _table_columns(conn, "units")
    match_parts = _match_sql(unit_columns, alias="u")
    batch_columns = _table_columns(conn, "batches")
    line_columns = _table_columns(conn, "production_lines")
    if (
        not serials
        or not match_parts
        or not {"unit_id", "batch_id", "status"} <= unit_columns
        or not {"batch_id", "status", "production_line_id"} <= batch_columns
        or not {"line_id", "status"} <= line_columns
    ):
        return result

    rows = conn.execute(
        text(
            "SELECT u.unit_id AS unit_id, b.production_line_id AS production_line_id "
            "FROM units u "
            "JOIN batches b ON b.batch_id=u.batch_id "
            "JOIN production_lines p ON p.line_id=b.production_line_id "
            f"WHERE ({' OR '.join(match_parts)}) AND u.status='Completed' "
            "AND b.status='In_Production' "
            "AND b.production_line_id IS NOT NULL AND TRIM(b.production_line_id)<>'' "
            "AND p.status='Busy' FOR UPDATE"
        ).bindparams(bindparam("sns", expanding=True)),
        {"sns": serials},
    ).mappings().all()
    if not rows:
        return result

    units_by_line: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        unit_id = str(row.get("unit_id") or "").strip()
        line_id = str(row.get("production_line_id") or "").strip()
        if unit_id and line_id:
            units_by_line[line_id].append(unit_id)
    if not units_by_line:
        return result

    all_unit_ids: list[str] = []
    for line_id, unit_ids in units_by_line.items():
        all_unit_ids.extend(unit_ids)
        set_parts = ["status='In_Production'", "production_line_id=:line_id"]
        if "updated_at" in unit_columns:
            set_parts.append("updated_at=:now_text")
        conn.execute(
            text(
                f"UPDATE units SET {', '.join(set_parts)} "
                "WHERE unit_id IN :ids AND status='Completed'"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": unit_ids, "line_id": line_id, "now_text": now_text},
        )

    ledger_columns = _table_columns(conn, "production_history_ledger")
    if {"unit_id", "status"} <= ledger_columns:
        ledger_set = ["status='In_Production'"]
        if "completed_at" in ledger_columns:
            ledger_set.append("completed_at=NULL")
        if "updated_at" in ledger_columns:
            ledger_set.append("updated_at=:now_text")
        conn.execute(
            text(
                f"UPDATE production_history_ledger SET {', '.join(ledger_set)} "
                "WHERE unit_id IN :ids AND status='Completed'"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": all_unit_ids, "now_text": now_text},
        )

    result["unit_ids"] = all_unit_ids
    result["affected_lines"] = sorted(units_by_line)
    return result
