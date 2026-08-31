from __future__ import annotations

from datetime import datetime

from sqlalchemy import text


def next_contract_no(conn, now: datetime | None = None) -> str:
    current = now or datetime.now()
    prefix = f"HT{current:%Y%m%d}"
    pattern = f"^{prefix}[0-9]{{4}}$"
    row = conn.execute(
        text(
            """
            SELECT MAX(seq_no) AS max_seq
            FROM (
                SELECT CAST(SUBSTRING(`合同号`, 11, 4) AS UNSIGNED) AS seq_no
                FROM factory_plan
                WHERE `合同号` REGEXP :pattern
                UNION ALL
                SELECT CAST(SUBSTRING(contract_id, 11, 4) AS UNSIGNED) AS seq_no
                FROM contract_records
                WHERE contract_id REGEXP :pattern
            ) existing_contracts
            """
        ),
        {"pattern": pattern},
    ).mappings().first()
    next_seq = int((row or {}).get("max_seq") or 0) + 1
    if next_seq > 9999:
        raise ValueError(f"{prefix} 当天合同号已超过 9999")
    return f"{prefix}{next_seq:04d}"


def contract_no_exists(conn, contract_no: str) -> bool:
    value = str(contract_no or "").strip()
    if not value:
        return False
    row = conn.execute(
        text("SELECT 1 FROM factory_plan WHERE `合同号` = :contract_no LIMIT 1"),
        {"contract_no": value},
    ).first()
    if row:
        return True
    row = conn.execute(
        text("SELECT 1 FROM contract_records WHERE contract_id = :contract_no LIMIT 1"),
        {"contract_no": value},
    ).first()
    return bool(row)
