#!/usr/bin/env python3
"""Retire the two shipped production cards of order SO-20260927-4EDE.

96-07-75 / 96-08-210 were reserved while still in production and shipped on
2026-09-30 without an inbound event. Shipping only changed
finished_goods_data, so the cards stayed on line-20 / line-19 and kept showing
as 在产已绑定.

The script verifies the exact expected state, creates backup tables, and reuses
the same production-card retirement helper as the shipping endpoint. Preview is
the default; pass --apply to write.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import bindparam, text

from crud.production_cards import retire_shipped_production_cards
from database import get_engine

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ORDER = "SO-20260927-4EDE"
CONTRACT = "HT202609040002"
SERIALS = ["96-07-75", "96-08-210"]
EXPECTED_LINES = {"96-07-75": "line-20", "96-08-210": "line-19"}


def _scalar(conn, sql: str, params: dict) -> int:
    return int(conn.execute(text(sql), params).scalar() or 0)


def load_state(conn) -> dict:
    sns_param = bindparam("sns", expanding=True)
    finished = [
        dict(row)
        for row in conn.execute(
            text(
                "SELECT `流水号`,`状态`,`占用订单号`,`合同号`,`批次号`,`更新时间` "
                "FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE"
            ).bindparams(sns_param),
            {"sns": SERIALS},
        ).mappings()
    ]
    units = [
        dict(row)
        for row in conn.execute(
            text(
                "SELECT u.unit_id, u.batch_id, u.status, u.production_line_id, "
                "u.contract_no, u.sales_id, "
                "COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) AS serial_no, "
                "b.batch_code, b.status AS batch_status, "
                "p.status AS line_status, p.current_batch_id "
                "FROM units u "
                "JOIN batches b ON b.batch_id=u.batch_id "
                "LEFT JOIN production_lines p ON p.line_id=u.production_line_id "
                "WHERE COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) "
                "IN :sns FOR UPDATE"
            ).bindparams(sns_param),
            {"sns": SERIALS},
        ).mappings()
    ]
    return {"finished_goods": finished, "units": units}


def validate(state: dict, conn) -> None:
    finished = state["finished_goods"]
    units = state["units"]
    if len(finished) != 2 or {row["流水号"] for row in finished} != set(SERIALS):
        raise RuntimeError(f"unexpected finished_goods rows: {finished}")
    for row in finished:
        if str(row["状态"] or "").strip() != "已出库":
            raise RuntimeError(f"machine is not shipped: {row}")
        if str(row["占用订单号"] or "").strip() != ORDER:
            raise RuntimeError(f"unexpected order binding: {row}")
        if str(row["合同号"] or "").strip() != CONTRACT:
            raise RuntimeError(f"unexpected contract binding: {row}")

    if len(units) != 2 or {str(row["production_line_id"]) for row in units} != set(EXPECTED_LINES.values()):
        raise RuntimeError(f"unexpected unit rows: {units}")
    for row in units:
        line_id = str(row["production_line_id"] or "").strip()
        serial = str(row["serial_no"] or "").strip()
        if str(row["status"] or "").strip() != "In_Production":
            raise RuntimeError(f"unit is not in production: {row}")
        if str(row["batch_status"] or "").strip() != "In_Production":
            raise RuntimeError(f"batch is not in production: {row}")
        if str(row["line_status"] or "").strip() != "Busy":
            raise RuntimeError(f"line is not busy: {row}")
        if str(row["contract_no"] or "").strip() != CONTRACT or str(row["sales_id"] or "").strip() != ORDER:
            raise RuntimeError(f"unit binding drifted: {row}")
        if EXPECTED_LINES.get(serial) != line_id:
            raise RuntimeError(f"unexpected line mapping: {row}")

    # Scope guard: these must be the only shipped machines still shown in production.
    active = _scalar(
        conn,
        "SELECT COUNT(*) FROM finished_goods_data fg "
        "JOIN units u ON COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) "
        "= TRIM(fg.`流水号`) COLLATE utf8mb4_general_ci "
        "WHERE TRIM(COALESCE(fg.`状态`, '')) IN ('已出库','已发货') "
        "AND u.status='In_Production'",
        {},
    )
    if active != len(SERIALS):
        raise RuntimeError(f"scope changed: {active} shipped machines are still in production")


def create_backups(conn, run_id: str, state: dict) -> dict[str, str]:
    ids = [row["unit_id"] for row in state["units"]]
    batch_ids = sorted({row["batch_id"] for row in state["units"]})
    line_ids = sorted({row["production_line_id"] for row in state["units"]})
    names = {
        "units": f"repair_backup_shipped_cards_{run_id}_units",
        "ledger": f"repair_backup_shipped_cards_{run_id}_ledger",
        "batches": f"repair_backup_shipped_cards_{run_id}_batches",
        "lines": f"repair_backup_shipped_cards_{run_id}_lines",
    }
    existing = [
        name
        for name in names.values()
        if _scalar(conn, "SELECT COUNT(*) FROM information_schema.tables "
                         "WHERE table_schema=DATABASE() AND table_name=:name", {"name": name})
    ]
    if existing:
        raise RuntimeError(f"backup tables already exist: {', '.join(existing)}")
    conn.execute(
        text(f"CREATE TABLE {names['units']} AS SELECT * FROM units WHERE unit_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    conn.execute(
        text(f"CREATE TABLE {names['ledger']} AS SELECT * FROM production_history_ledger "
             f"WHERE unit_id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    conn.execute(
        text(f"CREATE TABLE {names['batches']} AS SELECT * FROM batches WHERE batch_id IN :bids")
        .bindparams(bindparam("bids", expanding=True)),
        {"bids": batch_ids},
    )
    conn.execute(
        text(f"CREATE TABLE {names['lines']} AS SELECT * FROM production_lines WHERE line_id IN :lids")
        .bindparams(bindparam("lids", expanding=True)),
        {"lids": line_ids},
    )
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
    engine = get_engine()
    report: dict = {"order": ORDER, "serials": SERIALS, "apply": bool(args.apply), "run_id": run_id}
    backup_json: Path | None = None

    with engine.begin() as conn:
        state = load_state(conn)
        validate(state, conn)
        report["before"] = state
        if not args.apply:
            conn.execute(text("SELECT 1"))  # keep the read transaction explicit
        else:
            backups = create_backups(conn, run_id, state)
            report["backups"] = backups
            retired = retire_shipped_production_cards(conn, SERIALS, now_text)
            report["retired"] = retired
            remaining = _scalar(
                conn,
                "SELECT COUNT(*) FROM units "
                "WHERE COALESCE(NULLIF(TRIM(serial_no), ''), TRIM(forecast_serial_no)) IN "
                "(:s1,:s2) AND status='In_Production'",
                {"s1": SERIALS[0], "s2": SERIALS[1]},
            )
            if remaining:
                raise RuntimeError(f"repair failed: {remaining} units still in production")
            conn.execute(
                text(
                    "INSERT INTO sys_operation_log "
                    "(user_id,username,operate_time,module,action_type,biz_type,content,"
                    "serial_no,order_no,contract_no) VALUES "
                    "('SystemRepair','SystemRepair',NOW(),'发货复核','数据纠错','机台',"
                    ":content,:serial_no,:order_no,:contract_no)"
                ),
                [
                    {
                        "content": (
                            "按用户确认对在产预占直发的已出库机台执行单机台完工并移出产线；"
                            f"备份运行编号={run_id}；备份表={', '.join(report['backups'].values())}"
                        ),
                        "serial_no": serial,
                        "order_no": ORDER,
                        "contract_no": CONTRACT,
                    }
                    for serial in SERIALS
                ],
            )
            backup_dir = Path("data_repair_backups")
            backup_dir.mkdir(exist_ok=True)
            backup_json = backup_dir / f"shipped-production-cards-{run_id}.json"
            with backup_json.open("x", encoding="utf-8") as handle:
                json.dump({"state": state, "report": {**report, "backup_json": str(backup_json)}},
                          handle, ensure_ascii=False, default=str, indent=2)
            report["after"] = load_state(conn)
            report["backup_json"] = str(backup_json)

    print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
