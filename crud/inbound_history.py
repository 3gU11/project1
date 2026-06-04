from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from database import get_engine


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_serials(serial_nos: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in serial_nos or []:
        serial = _clean(raw)
        if serial and serial not in seen:
            seen.add(serial)
            result.append(serial)
    return result


def ensure_inbound_history_table(conn: Connection | None = None) -> None:
    owns_conn = conn is None
    engine = get_engine()
    if owns_conn:
        conn_ctx = engine.begin()
        conn = conn_ctx.__enter__()
    else:
        conn_ctx = None

    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inbound_history (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                serial_no VARCHAR(100) NOT NULL,
                inbound_time DATETIME NOT NULL,
                source VARCHAR(50) NOT NULL DEFAULT '',
                slot_code VARCHAR(100) NOT NULL DEFAULT '',
                operator VARCHAR(100) NOT NULL DEFAULT '',
                batch_no VARCHAR(100) NOT NULL DEFAULT '',
                model VARCHAR(255) NOT NULL DEFAULT '',
                customer VARCHAR(255) NOT NULL DEFAULT '',
                dealer VARCHAR(255) NOT NULL DEFAULT '',
                contract_no VARCHAR(100) NOT NULL DEFAULT '',
                order_no VARCHAR(100) NOT NULL DEFAULT '',
                status_before VARCHAR(50) NOT NULL DEFAULT '',
                status_after VARCHAR(50) NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_inbound_history_event (serial_no, inbound_time, source),
                INDEX idx_inbound_history_time (inbound_time),
                INDEX idx_inbound_history_serial (serial_no),
                INDEX idx_inbound_history_batch (batch_no),
                INDEX idx_inbound_history_model (model),
                INDEX idx_inbound_history_customer (customer)
            )
        """))
    finally:
        if owns_conn and conn_ctx is not None:
            conn_ctx.__exit__(None, None, None)


def record_inbound_history(
    conn: Connection,
    serial_nos: Iterable[Any],
    *,
    source: str,
    operator: str = "",
    slot_code: str = "",
    inbound_time: datetime | str | None = None,
    status_before: str | dict[str, str] = "",
    status_after: str = "",
) -> int:
    serials = _normalize_serials(serial_nos)
    if not serials:
        return 0

    ensure_inbound_history_table(conn)
    inbound_at = inbound_time or datetime.now()

    rows = conn.execute(
        text("""
            SELECT
                `流水号` AS serial_no,
                `批次号` AS batch_no,
                `机型` AS model,
                `客户` AS customer,
                `代理商` AS dealer,
                `合同号` AS contract_no,
                `占用订单号` AS order_no,
                `状态` AS current_status,
                `Location_Code` AS current_slot
            FROM finished_goods_data
            WHERE `流水号` IN :serials
        """).bindparams(bindparam("serials", expanding=True)),
        {"serials": serials},
    ).mappings().all()

    status_map = status_before if isinstance(status_before, dict) else {}
    fallback_before = "" if isinstance(status_before, dict) else _clean(status_before)
    payload = []
    for row in rows:
        serial = _clean(row.get("serial_no"))
        payload.append({
            "serial_no": serial,
            "inbound_time": inbound_at,
            "source": _clean(source),
            "slot_code": _clean(slot_code) or _clean(row.get("current_slot")),
            "operator": _clean(operator),
            "batch_no": _clean(row.get("batch_no")),
            "model": _clean(row.get("model")),
            "customer": _clean(row.get("customer")),
            "dealer": _clean(row.get("dealer")),
            "contract_no": _clean(row.get("contract_no")),
            "order_no": _clean(row.get("order_no")),
            "status_before": _clean(status_map.get(serial, fallback_before)),
            "status_after": _clean(status_after) or _clean(row.get("current_status")),
        })

    if not payload:
        return 0

    result = conn.execute(text("""
        INSERT IGNORE INTO inbound_history (
            serial_no, inbound_time, source, slot_code, operator,
            batch_no, model, customer, dealer, contract_no, order_no,
            status_before, status_after
        ) VALUES (
            :serial_no, :inbound_time, :source, :slot_code, :operator,
            :batch_no, :model, :customer, :dealer, :contract_no, :order_no,
            :status_before, :status_after
        )
    """), payload)
    return int(result.rowcount or 0)


def backfill_inbound_history_from_logs(conn: Connection | None = None) -> int:
    owns_conn = conn is None
    engine = get_engine()
    if owns_conn:
        conn_ctx = engine.begin()
        conn = conn_ctx.__enter__()
    else:
        conn_ctx = None

    try:
        ensure_inbound_history_table(conn)
        result = conn.execute(text("""
            INSERT IGNORE INTO inbound_history (
                serial_no, inbound_time, source, slot_code, operator,
                batch_no, model, customer, dealer, contract_no, order_no,
                status_before, status_after
            )
            SELECT
                tl.`流水号` AS serial_no,
                tl.`时间` AS inbound_time,
                tl.`操作类型` AS source,
                COALESCE(fg.`Location_Code`, '') AS slot_code,
                COALESCE(tl.`操作员`, '') AS operator,
                COALESCE(fg.`批次号`, sh.`批次号`, '') AS batch_no,
                COALESCE(fg.`机型`, sh.`机型`, '') AS model,
                COALESCE(fg.`客户`, sh.`客户`, '') AS customer,
                COALESCE(fg.`代理商`, sh.`代理商`, '') AS dealer,
                COALESCE(fg.`合同号`, sh.`合同号`, '') AS contract_no,
                COALESCE(fg.`占用订单号`, sh.`占用订单号`, '') AS order_no,
                '待入库' AS status_before,
                COALESCE(fg.`状态`, sh.`状态`, '') AS status_after
            FROM transaction_log tl
            LEFT JOIN finished_goods_data fg
                ON fg.`流水号` COLLATE utf8mb4_general_ci = tl.`流水号` COLLATE utf8mb4_general_ci
            LEFT JOIN shipping_history sh
                ON sh.`流水号` COLLATE utf8mb4_general_ci = tl.`流水号` COLLATE utf8mb4_general_ci
            WHERE tl.`流水号` IS NOT NULL
                AND TRIM(tl.`流水号`) <> ''
                AND (
                    tl.`操作类型` = '直接配货-自动入库'
                    OR tl.`操作类型` = '配货自动入库'
                    OR (
                        tl.`操作类型` LIKE '%入库%'
                        AND tl.`操作类型` NOT LIKE '%退回%'
                        AND tl.`操作类型` NOT LIKE '%释放%'
                        AND tl.`操作类型` NOT LIKE '%撤回%'
                    )
                )
                AND COALESCE(fg.`状态`, sh.`状态`, '') <> '待入库'
                AND COALESCE(fg.`状态`, sh.`状态`, '') <> ''
        """))
        return int(result.rowcount or 0)
    finally:
        if owns_conn and conn_ctx is not None:
            conn_ctx.__exit__(None, None, None)
