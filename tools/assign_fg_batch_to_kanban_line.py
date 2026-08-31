#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception as exc:  # pragma: no cover - depends on operator runtime
    print(f"ERROR: PyMySQL is required: {exc}", file=sys.stderr)
    print("Use the project .venv Python or install pymysql for the selected Python.", file=sys.stderr)
    raise


FG_BATCH = "\u6279\u6b21\u53f7"
FG_MODEL = "\u673a\u578b"
FG_SERIAL = "\u6d41\u6c34\u53f7"
FG_STATUS = "\u72b6\u6001"
FG_PENDING = "\u5f85\u5165\u5e93"
FG_DUE = "\u9884\u8ba1\u5165\u5e93\u65f6\u95f4"
FG_CUSTOMER = "\u5ba2\u6237"
FG_DEALER = "\u4ee3\u7406\u5546"
FG_REMARK = "\u5408\u540c\u5907\u6ce8"
FG_CONTRACT = "\u5408\u540c\u53f7"
FG_ORDER_OCCUPIED = "\u5360\u7528\u8ba2\u5355\u53f7"
FG_ORDER = "\u8ba2\u5355\u53f7"

FP_STATUS = "\u72b6\u6001"
FP_PENDING = "\u5f85\u89c4\u5212"
FP_PLANNED = "\u5df2\u89c4\u5212"

LINE = "\u4ea7\u7ebf"
SMALL = "\u4e2d\u5c0f\u578b"
LARGE = "\u4e2d\u5927\u578b"
SPECIAL_CN = "\u7279\u6b8a"
SMALL_LINE = "\u4e2d\u5c0f\u578b\u673a\u578b\u7ebf"
LARGE_LINE = "\u4e2d\u5927\u578b\u673a\u578b\u7ebf"
SPECIAL_LINE = "\u7279\u6b8a\u673a\u578b\u7ebf"

MAJOR = {
    "SMALL_G": "\u4e2d\u5c0f\u578bG",
    "SMALL_XS": "\u4e2d\u5c0f\u578bXS",
    "LARGE_XS": "\u4e2d\u5927\u578bXS",
    "SMALL_AUTO": "\u4e2d\u5c0f\u578bAUTO",
    "LARGE_AUTO": "\u4e2d\u5927\u578bAUTO",
    "SPECIAL": SPECIAL_CN,
}

CATEGORY_ORDER = ["SMALL_G", "SMALL_XS", "LARGE_XS", "SMALL_AUTO", "LARGE_AUTO", "SPECIAL"]
CATEGORY_INFO = {
    "SMALL_G": {"family": "G", "region": "SMALL", "capacity": 30},
    "SMALL_XS": {"family": "XS", "region": "SMALL", "capacity": 30},
    "LARGE_XS": {"family": "XS", "region": "LARGE", "capacity": 16},
    "SMALL_AUTO": {"family": "AUTO", "region": "SMALL", "capacity": 27},
    "LARGE_AUTO": {"family": "AUTO", "region": "LARGE", "capacity": 16},
    "SPECIAL": {"family": "SPECIAL", "region": "SPECIAL", "capacity": 15},
}


class ToolError(RuntimeError):
    pass


def qident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def clean(value: Any) -> str:
    return str(value or "").strip()


def none_if_blank(value: Any) -> Any:
    value = clean(value)
    return value if value else None


def date_only(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or value == "":
        return None
    return str(value)[:10]


def dt_for_sort(value: Any) -> str:
    value = date_only(value)
    return str(value) if value else "2999-12-31"


def digest(value: str, size: int = 16) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:size].upper()


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def table_columns(cur, table: str) -> set[str]:
    if not table_exists(cur, table):
        return set()
    cur.execute(f"SHOW COLUMNS FROM {qident(table)}")
    return {str(row["Field"]) for row in cur.fetchall()}


def require_tables(cur, tables: list[str]) -> None:
    missing = [table for table in tables if not table_exists(cur, table)]
    if missing:
        raise ToolError("missing required tables: " + ", ".join(missing))


def require_columns(cur, table: str, cols: list[str]) -> None:
    existing = table_columns(cur, table)
    missing = [col for col in cols if col not in existing]
    if missing:
        raise ToolError(f"{table} missing required columns: " + ", ".join(missing))


def select_expr(cols: set[str], col: str, alias: str) -> str:
    if col in cols:
        return f"{qident(col)} AS {alias}"
    return f"NULL AS {alias}"


def region_label(region: str | None) -> str:
    return {"SMALL": "small", "LARGE": "large", "SPECIAL": "special"}.get(clean(region).upper(), "-")


def is_large_model(upper: str) -> bool:
    return any(token in upper for token in ("7055", "8055", "8060"))


def category_from_family_or_category(value: str, model_upper: str = "") -> str:
    raw = clean(value)
    upper = raw.upper()
    if not raw:
        return ""

    if raw in (MAJOR["SMALL_G"], "\u5c0f\u673aG", f"{SMALL}G") or upper == "G":
        return "SMALL_G"
    if raw in (MAJOR["SMALL_XS"], "\u5c0f\u673aXS", f"{SMALL}XS"):
        return "SMALL_XS"
    if raw in (MAJOR["LARGE_XS"], "\u5927\u673aXS", f"{LARGE}XS"):
        return "LARGE_XS"
    if raw in (MAJOR["SMALL_AUTO"], "\u5c0f\u673aAUTO", f"{SMALL}AUTO"):
        return "SMALL_AUTO"
    if raw in (MAJOR["LARGE_AUTO"], "\u5927\u673aAUTO", f"{LARGE}AUTO"):
        return "LARGE_AUTO"
    if raw == SPECIAL_CN or "SPECIAL" in upper or upper == "FT":
        return "SPECIAL"
    if upper == "XS":
        return "LARGE_XS" if is_large_model(model_upper) else "SMALL_XS"
    if upper == "AUTO":
        return "LARGE_AUTO" if is_large_model(model_upper) else "SMALL_AUTO"
    if "AUTO" in upper:
        return "LARGE_AUTO" if "LARGE" in upper or LARGE in raw else "SMALL_AUTO"
    if "XS" in upper:
        return "LARGE_XS" if "LARGE" in upper or LARGE in raw else "SMALL_XS"
    if SPECIAL_CN in raw:
        return "SPECIAL"
    return ""


def classify_model(model: str, family_map: dict[str, str]) -> dict[str, Any]:
    model_name = clean(model)
    upper = model_name.upper()
    category = category_from_family_or_category(family_map.get(upper, ""), upper)
    if not category:
        if upper == "FH-300C":
            category = "SMALL_G"
        elif upper.startswith("FH-") or upper.startswith("FL-") or upper.startswith("FR-1080") or upper.startswith("FR-8080") or upper.startswith("FR-1100"):
            category = "SPECIAL"
        elif "AUTO" in upper:
            category = "LARGE_AUTO" if is_large_model(upper) else "SMALL_AUTO"
        elif "XS" in upper:
            category = "LARGE_XS" if is_large_model(upper) else "SMALL_XS"
        elif upper.endswith("G") or re.search(r"\bFR-\d+G\b", upper):
            category = "SMALL_G"
        else:
            category = "SPECIAL"

    info = dict(CATEGORY_INFO[category])
    info["category"] = category
    info["major"] = MAJOR[category]
    return info


def load_family_map(cur) -> dict[str, str]:
    if not table_exists(cur, "model_dictionary"):
        return {}
    cols = table_columns(cur, "model_dictionary")
    if "model_name" not in cols or "model_family" not in cols:
        return {}
    enabled_clause = "WHERE enabled = 1" if "enabled" in cols else ""
    cur.execute(f"SELECT model_name, model_family FROM model_dictionary {enabled_clause}")
    out: dict[str, str] = {}
    for row in cur.fetchall():
        name = clean(row.get("model_name")).upper()
        family = clean(row.get("model_family"))
        if name and family:
            out[name] = family
    return out


def load_capacity_defaults(cur) -> dict[str, int]:
    caps = {"G": 30, "XS": 30, "AUTO": 27}
    if table_exists(cur, "system_config"):
        cols = table_columns(cur, "system_config")
        if {"config_key", "config_value"}.issubset(cols):
            cur.execute("SELECT config_value FROM system_config WHERE config_key = 'model_capacity' LIMIT 1")
            row = cur.fetchone()
            if row and row.get("config_value"):
                try:
                    data = row["config_value"]
                    if isinstance(data, str):
                        data = json.loads(data)
                    for key in caps:
                        value = int(data.get(key) or 0)
                        if value > 0:
                            caps[key] = value
                except Exception:
                    pass
    return {
        "SMALL_G": caps["G"],
        "SMALL_XS": caps["XS"],
        "LARGE_XS": 16,
        "SMALL_AUTO": caps["AUTO"],
        "LARGE_AUTO": 16,
        "SPECIAL": 15,
    }


def infer_line_region(line: dict[str, Any]) -> str:
    for key in ("region", "model_type", "line_name", "line_id"):
        value = clean(line.get(key))
        upper = value.upper()
        if upper in ("SMALL", "LARGE", "SPECIAL"):
            return upper
        if SPECIAL_CN in value or "SPECIAL" in upper:
            return "SPECIAL"
        if LARGE in value or "LARGE" in upper:
            return "LARGE"
        if SMALL in value or "SMALL" in upper:
            return "SMALL"

    order = line.get("display_order")
    try:
        order_int = int(order)
        if 1 <= order_int <= 13:
            return "SMALL"
        if 14 <= order_int <= 18:
            return "LARGE"
        if 19 <= order_int <= 20:
            return "SPECIAL"
    except Exception:
        pass

    match = re.search(r"(\d+)", clean(line.get("line_id")))
    if match:
        n = int(match.group(1))
        if 1 <= n <= 13:
            return "SMALL"
        if 14 <= n <= 18:
            return "LARGE"
        if 19 <= n <= 20:
            return "SPECIAL"
    return ""


def default_line_def(index: int) -> tuple[str, str, int, str, str]:
    if index <= 13:
        return f"line-{index:02d}", f"{LINE} {index:02d} {SMALL}", index, SMALL_LINE, "SMALL"
    if index <= 18:
        return f"line-{index:02d}", f"{LINE} {index:02d} {LARGE}", index, LARGE_LINE, "LARGE"
    return f"line-{index:02d}", f"{LINE} {index:02d} {SPECIAL_CN}", index, SPECIAL_LINE, "SPECIAL"


def ensure_default_lines(cur, dry_run: bool) -> int:
    cur.execute("SELECT COUNT(*) AS cnt FROM production_lines")
    count = int(cur.fetchone()["cnt"] or 0)
    if count > 0:
        return 0
    if dry_run:
        print("DRY RUN: would create 20 default production lines.")
        return 20

    cols = table_columns(cur, "production_lines")
    created = 0
    for i in range(1, 21):
        line_id, line_name, display_order, model_type, region = default_line_def(i)
        values: dict[str, Any] = {
            "line_id": line_id,
            "line_name": line_name,
            "display_order": display_order,
            "status": "Idle",
            "current_batch_id": None,
            "model_type": model_type,
            "region": region,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        insert_values = {k: v for k, v in values.items() if k in cols}
        insert_row(cur, "production_lines", insert_values)
        created += 1
    return created


def fetch_batch_summaries(cur, limit: int) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            TRIM(COALESCE({qident(FG_BATCH)}, '')) AS batch_code,
            COUNT(*) AS total_units,
            SUM(CASE WHEN TRIM(COALESCE({qident(FG_SERIAL)}, '')) = '' THEN 1 ELSE 0 END) AS blank_serials,
            MIN({qident(FG_DUE)}) AS due_min,
            MAX({qident(FG_DUE)}) AS due_max,
            GROUP_CONCAT(DISTINCT {qident(FG_MODEL)} ORDER BY {qident(FG_MODEL)} SEPARATOR ', ') AS models
        FROM finished_goods_data
        WHERE {qident(FG_STATUS)} = %s
          AND TRIM(COALESCE({qident(FG_BATCH)}, '')) <> ''
        GROUP BY TRIM(COALESCE({qident(FG_BATCH)}, ''))
        ORDER BY MIN(COALESCE({qident(FG_DUE)}, '2999-12-31')), batch_code
        LIMIT %s
    """
    cur.execute(sql, (FG_PENDING, limit))
    rows = list(cur.fetchall())
    codes = [row["batch_code"] for row in rows if row.get("batch_code")]
    if not codes:
        return rows

    placeholders = ",".join(["%s"] * len(codes))
    cur.execute(
        f"""
        SELECT
            TRIM(COALESCE(b.batch_code, '')) AS batch_code,
            COUNT(DISTINCT b.batch_id) AS batch_records,
            COUNT(DISTINCT CASE WHEN b.status = 'In_Production' THEN b.batch_id END) AS active_batches,
            COUNT(DISTINCT u.unit_id) AS kanban_units,
            GROUP_CONCAT(DISTINCT CONCAT(COALESCE(pl.line_id, b.production_line_id, ''), '/', b.status) SEPARATOR '; ') AS kanban
        FROM batches b
        LEFT JOIN units u ON u.batch_id = b.batch_id
        LEFT JOIN production_lines pl ON pl.line_id = b.production_line_id
        WHERE TRIM(COALESCE(b.batch_code, '')) IN ({placeholders})
        GROUP BY TRIM(COALESCE(b.batch_code, ''))
        """,
        codes,
    )
    kanban_by_code = {row["batch_code"]: row for row in cur.fetchall()}
    for row in rows:
        row["kanban"] = kanban_by_code.get(row["batch_code"], {})
    return rows


def fetch_lines(cur) -> list[dict[str, Any]]:
    cols = table_columns(cur, "production_lines")
    optional = []
    group_cols = ["pl.line_id", "pl.line_name", "pl.status", "pl.display_order", "pl.current_batch_id"]
    if "model_type" in cols:
        optional.append("pl.model_type")
        group_cols.append("pl.model_type")
    else:
        optional.append("NULL AS model_type")
    if "region" in cols:
        optional.append("pl.region")
        group_cols.append("pl.region")
    else:
        optional.append("NULL AS region")
    optional_sql = ",\n            ".join(optional)
    group_sql = ", ".join(group_cols)
    cur.execute(
        f"""
        SELECT
            pl.line_id,
            pl.line_name,
            pl.status,
            pl.display_order,
            pl.current_batch_id,
            {optional_sql},
            COUNT(DISTINCT CASE WHEN b.status = 'In_Production' THEN b.batch_id END) AS active_batches,
            COUNT(DISTINCT CASE WHEN u.status = 'In_Production' THEN u.unit_id END) AS active_units,
            GROUP_CONCAT(DISTINCT CASE WHEN b.status = 'In_Production' THEN COALESCE(b.batch_code, b.batch_id) END SEPARATOR ', ') AS active_batch_codes
        FROM production_lines pl
        LEFT JOIN batches b ON b.production_line_id = pl.line_id
        LEFT JOIN units u ON u.production_line_id = pl.line_id
        GROUP BY {group_sql}
        ORDER BY pl.display_order ASC, pl.line_id ASC
        """
    )
    return list(cur.fetchall())


def print_batches(rows: list[dict[str, Any]]) -> None:
    print("\nPending finished-goods batches:")
    if not rows:
        print("  (none)")
        return
    for idx, row in enumerate(rows, 1):
        kanban = row.get("kanban") or {}
        kanban_text = clean(kanban.get("kanban")) or "-"
        print(
            f"{idx:>3}. {row['batch_code']:<12} units={int(row['total_units'] or 0):>3} "
            f"blank_sn={int(row['blank_serials'] or 0):>2} due={date_only(row.get('due_min')) or '-'} "
            f"models={clean(row.get('models'))[:80] or '-'} kanban={kanban_text}"
        )


def print_lines(rows: list[dict[str, Any]]) -> None:
    print("\nProduction lines:")
    if not rows:
        print("  (none)")
        return
    for idx, row in enumerate(rows, 1):
        inferred = infer_line_region(row)
        print(
            f"{idx:>3}. {row['line_id']:<10} {clean(row.get('line_name')):<18} "
            f"status={clean(row.get('status')):<5} region={region_label(inferred):<7} "
            f"active_batches={int(row.get('active_batches') or 0):>2} "
            f"active_units={int(row.get('active_units') or 0):>3} "
            f"codes={clean(row.get('active_batch_codes')) or '-'}"
        )


def choose_batch(cur, batch_code: str, limit: int) -> str:
    if clean(batch_code):
        return clean(batch_code)
    rows = fetch_batch_summaries(cur, limit)
    print_batches(rows)
    if not rows:
        raise ToolError("no pending finished-goods batches found")
    answer = input("\nSelect batch number or type batch_code: ").strip()
    if answer.isdigit():
        idx = int(answer)
        if 1 <= idx <= len(rows):
            return clean(rows[idx - 1]["batch_code"])
    if answer:
        return answer
    raise ToolError("batch_code is required")


def choose_line(cur, line_id: str) -> str:
    if clean(line_id):
        return clean(line_id)
    rows = fetch_lines(cur)
    print_lines(rows)
    if not rows:
        raise ToolError("no production lines found; rerun with --ensure-default-lines if this is a fresh V8 schema")
    answer = input("\nSelect line number or type line_id: ").strip()
    if answer.isdigit():
        idx = int(answer)
        if 1 <= idx <= len(rows):
            return clean(rows[idx - 1]["line_id"])
    if answer:
        return answer
    raise ToolError("line_id is required")


def load_source_rows(cur, batch_code: str, all_statuses: bool = False, include_shipped: bool = False) -> list[dict[str, Any]]:
    cols = table_columns(cur, "finished_goods_data")
    order_col = FG_ORDER_OCCUPIED if FG_ORDER_OCCUPIED in cols else FG_ORDER
    select_cols = [
        select_expr(cols, FG_BATCH, "batch_code"),
        select_expr(cols, FG_MODEL, "model"),
        select_expr(cols, FG_SERIAL, "serial_no"),
        select_expr(cols, FG_STATUS, "fg_status"),
        select_expr(cols, FG_DUE, "due_dt"),
        select_expr(cols, FG_CUSTOMER, "customer"),
        select_expr(cols, FG_DEALER, "dealer"),
        select_expr(cols, FG_REMARK, "remark"),
        select_expr(cols, FG_CONTRACT, "contract_no"),
        select_expr(cols, order_col, "order_no"),
    ]
    order_by = []
    if FG_DUE in cols:
        order_by.append(f"COALESCE({qident(FG_DUE)}, '2999-12-31')")
    if FG_SERIAL in cols:
        order_by.append(qident(FG_SERIAL))
    order_sql = ", ".join(order_by) or "1"
    status_sql = f"AND {qident(FG_STATUS)} = %s"
    params: list[Any] = [batch_code, FG_PENDING]
    if all_statuses:
        status_sql = ""
        params = [batch_code]
    if all_statuses and not include_shipped:
        status_sql = f"AND TRIM(COALESCE({qident(FG_STATUS)}, '')) <> %s"
        params = [batch_code, "\u5df2\u51fa\u5e93"]
    cur.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM finished_goods_data
        WHERE TRIM(COALESCE({qident(FG_BATCH)}, '')) = %s
          {status_sql}
        ORDER BY {order_sql}
        """,
        params,
    )
    return list(cur.fetchall())


def load_line(cur, line_id: str) -> dict[str, Any] | None:
    cols = table_columns(cur, "production_lines")
    optional = []
    if "model_type" in cols:
        optional.append("model_type")
    else:
        optional.append("NULL AS model_type")
    if "region" in cols:
        optional.append("region")
    else:
        optional.append("NULL AS region")
    cur.execute(
        f"""
        SELECT line_id, line_name, status, display_order, current_batch_id,
               {", ".join(optional)}
        FROM production_lines
        WHERE line_id = %s
        """,
        (line_id,),
    )
    return cur.fetchone()


def active_batches_for_line(cur, line_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT batch_id, batch_code, model_type, status, production_line_id
        FROM batches
        WHERE production_line_id = %s AND status = 'In_Production'
        ORDER BY COALESCE(batch_code, ''), batch_no, batch_id
        """,
        (line_id,),
    )
    return list(cur.fetchall())


def load_batches(cur, batch_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not batch_ids:
        return {}
    placeholders = ",".join(["%s"] * len(batch_ids))
    cur.execute(f"SELECT * FROM batches WHERE batch_id IN ({placeholders})", batch_ids)
    return {row["batch_id"]: row for row in cur.fetchall()}


def load_existing_units(cur, serials: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not serials:
        return {}
    placeholders = ",".join(["%s"] * len(serials))
    params = serials + serials
    cur.execute(
        f"""
        SELECT
            u.*,
            b.batch_code AS existing_batch_code,
            b.status AS existing_batch_status,
            b.production_line_id AS existing_batch_line_id
        FROM units u
        LEFT JOIN batches b ON b.batch_id = u.batch_id
        WHERE TRIM(COALESCE(u.serial_no, '')) IN ({placeholders})
           OR TRIM(COALESCE(u.forecast_serial_no, '')) IN ({placeholders})
        """,
        params,
    )
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    serial_set = set(serials)
    seen_pairs: set[tuple[str, str]] = set()
    for row in cur.fetchall():
        for key in ("serial_no", "forecast_serial_no"):
            sn = clean(row.get(key))
            unit_id = clean(row.get("unit_id"))
            pair = (sn, unit_id)
            if sn in serial_set and pair not in seen_pairs:
                out[sn].append(row)
                seen_pairs.add(pair)
    return out


def batch_id_for(batch_code: str, category: str) -> str:
    return "FGMAN-" + digest(batch_code + "|" + category, 18)


def unit_id_for(serial: str, batch_id: str = "") -> str:
    key = serial if not batch_id else serial + "|" + batch_id
    return "FGU-" + digest(key, 24)


def batch_no_for(batch_code: str, seq: int) -> int:
    nums = re.findall(r"\d+", batch_code)
    if len(nums) >= 2:
        return int(nums[0]) * 1000 + int(nums[1]) * 10 + seq
    if len(nums) == 1:
        return int(nums[0]) * 10 + seq
    return int(digest(batch_code, 6), 16) % 900000 + seq


def build_plan(cur, args: argparse.Namespace, batch_code: str, line_id: str) -> dict[str, Any]:
    require_tables(cur, ["finished_goods_data", "production_lines", "batches", "units", "production_history_ledger"])
    require_columns(cur, "finished_goods_data", [FG_BATCH, FG_MODEL, FG_SERIAL, FG_STATUS])
    require_columns(cur, "production_lines", ["line_id", "line_name", "status", "display_order", "current_batch_id"])
    require_columns(cur, "batches", ["batch_id", "batch_no", "batch_code", "model_type", "capacity", "status", "production_line_id"])
    require_columns(cur, "units", ["unit_id", "serial_no", "batch_id", "slot_index", "model_type", "production_line_id", "status"])

    line = load_line(cur, line_id)
    if not line:
        raise ToolError(f"production line not found: {line_id}")
    line_region = infer_line_region(line)

    source_rows = load_source_rows(cur, batch_code, all_statuses=args.all_statuses, include_shipped=args.include_shipped)
    if not source_rows:
        if args.allow_empty_batch:
            source_rows = []
        else:
            scope = "finished-goods rows" if args.all_statuses else "pending finished-goods rows"
            raise ToolError(f"no {scope} found for batch_code={batch_code}")

    family_map = load_family_map(cur)
    capacity_defaults = load_capacity_defaults(cur)

    if not source_rows and args.allow_empty_batch:
        placeholder_category = {
            "SMALL": "SMALL_XS",
            "LARGE": "LARGE_XS",
            "SPECIAL": "SPECIAL",
        }.get(line_region or "", "SPECIAL")
        info = dict(CATEGORY_INFO[placeholder_category])
        group_items = [
            {
                "category": placeholder_category,
                "info": info,
                "major": MAJOR[placeholder_category],
                "family": info["family"],
                "region": info["region"],
                "batch_id": batch_id_for(batch_code, placeholder_category),
                "batch_no": batch_no_for(batch_code, 1),
                "default_capacity": int(capacity_defaults.get(placeholder_category, info["capacity"])),
                "capacity": int(capacity_defaults.get(placeholder_category, info["capacity"])),
                "rows": [],
            }
        ]
        target_batch_ids = [group["batch_id"] for group in group_items]
        existing_batches = load_batches(cur, target_batch_ids)
        active_batches = active_batches_for_line(cur, line_id)
        active_foreign = [b for b in active_batches if b["batch_id"] not in set(target_batch_ids)]
        conflicts = []
        if (clean(line.get("status")) == "Busy" or active_foreign) and active_foreign and not (args.force or args.replace_line):
            details = ", ".join(f"{b['batch_id']}({clean(b.get('batch_code')) or '-'})" for b in active_foreign)
            conflicts.append(f"line {line_id} is busy with other active batch(es): {details}; use --force or --replace-line if this is intentional")
        batch_actions = Counter()
        for group in group_items:
            if group["batch_id"] in existing_batches:
                batch_actions["update"] += 1
            else:
                batch_actions["insert"] += 1
        return {
            "batch_code": batch_code,
            "line_id": line_id,
            "line": line,
            "line_region": line_region,
            "source_rows": [],
            "blank_serials": [],
            "serials": [],
            "groups": group_items,
            "existing_batches": existing_batches,
            "existing_units": {},
            "active_foreign_batches": active_foreign,
            "conflicts": conflicts,
            "unit_actions": Counter(),
            "batch_actions": batch_actions,
            "placeholder": True,
        }

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blank_serials = []
    serials = []
    seen_serials = set()
    for row in source_rows:
        serial = clean(row.get("serial_no"))
        if not serial:
            blank_serials.append(row)
            continue
        if serial in seen_serials:
            continue
        seen_serials.add(serial)
        info = classify_model(clean(row.get("model")), family_map)
        row["_category"] = info["category"]
        row["_category_info"] = info
        groups[info["category"]].append(row)
        serials.append(serial)

    if not serials:
        raise ToolError(f"batch_code={batch_code} has no usable serial numbers")

    ordered_categories = [cat for cat in CATEGORY_ORDER if cat in groups]
    group_items = []
    for idx, category in enumerate(ordered_categories, 1):
        info = dict(CATEGORY_INFO[category])
        info["category"] = category
        info["major"] = MAJOR[category]
        rows = sorted(groups[category], key=lambda r: (dt_for_sort(r.get("due_dt")), clean(r.get("serial_no"))))
        default_capacity = int(capacity_defaults.get(category, info["capacity"]))
        capacity = max(default_capacity, len(rows))
        group_items.append(
            {
                "category": category,
                "info": info,
                "major": MAJOR[category],
                "family": info["family"],
                "region": info["region"],
                "batch_id": batch_id_for(batch_code, category),
                "batch_no": batch_no_for(batch_code, idx),
                "default_capacity": default_capacity,
                "capacity": capacity,
                "rows": rows,
            }
        )

    target_batch_ids = [group["batch_id"] for group in group_items]
    existing_batches = load_batches(cur, target_batch_ids)
    existing_units = load_existing_units(cur, serials)
    active_batches = active_batches_for_line(cur, line_id)

    conflicts = []
    if line_region and not args.force:
        mismatches = [g for g in group_items if g["region"] != line_region]
        if mismatches:
            details = ", ".join(f"{g['major']}->{region_label(g['region'])}" for g in mismatches)
            conflicts.append(f"line region is {region_label(line_region)}, but selected batch has {details}; use --force to override")

    active_foreign = [b for b in active_batches if b["batch_id"] not in set(target_batch_ids)]
    if (clean(line.get("status")) == "Busy" or active_foreign) and active_foreign and not (args.force or args.replace_line):
        details = ", ".join(f"{b['batch_id']}({clean(b.get('batch_code')) or '-'})" for b in active_foreign)
        conflicts.append(f"line {line_id} is busy with other active batch(es): {details}; use --force or --replace-line if this is intentional")

    for group in group_items:
        existing = existing_batches.get(group["batch_id"])
        if not existing:
            continue
        status = clean(existing.get("status"))
        existing_line = clean(existing.get("production_line_id"))
        if status == "Completed":
            conflicts.append(f"target batch {group['batch_id']} already completed; not reopening it")
        if status == "In_Production" and existing_line and existing_line != line_id and not (args.force and args.reassign_existing):
            conflicts.append(
                f"target batch {group['batch_id']} is already in production on {existing_line}; use --force --reassign-existing to move it"
            )

    unit_actions = Counter()
    duplicate_serials = []
    serial_to_target_group = {}
    for group in group_items:
        for row in group["rows"]:
            serial_to_target_group[clean(row.get("serial_no"))] = group

    for serial in serials:
        existing_list = existing_units.get(serial, [])
        group = serial_to_target_group[serial]
        if len(existing_list) > 1:
            duplicate_serials.append(serial)
            continue
        if not existing_list:
            unit_actions["insert"] += 1
            continue

        existing = existing_list[0]
        status = clean(existing.get("status"))
        old_batch = clean(existing.get("batch_id"))
        old_line = clean(existing.get("production_line_id"))
        if status == "Completed" and not args.reopen_completed:
            conflicts.append(
                f"serial {serial} already has completed unit {existing.get('unit_id')}; use --reopen-completed to put it back on a line"
            )
            unit_actions["completed_conflict"] += 1
            continue
        if status == "Completed" and args.reopen_completed:
            unit_actions["reopen_completed"] += 1
            continue
        if status == "In_Production" and old_line and old_line != line_id:
            if not (args.force and args.reassign_existing):
                conflicts.append(
                    f"serial {serial} is already in production on {old_line}; use --force --reassign-existing to move it"
                )
                unit_actions["line_conflict"] += 1
                continue
            unit_actions["reassign"] += 1
            continue
        if old_batch != group["batch_id"] and not args.reassign_existing:
            conflicts.append(
                f"serial {serial} already exists in batch {old_batch or '-'}; use --reassign-existing to attach it to this batch"
            )
            unit_actions["batch_conflict"] += 1
            continue
        if old_batch != group["batch_id"] or old_line != line_id:
            unit_actions["reassign"] += 1
        elif status != "In_Production":
            unit_actions["update"] += 1
        else:
            unit_actions["unchanged"] += 1

    if duplicate_serials:
        conflicts.append("duplicate unit records found for serial(s): " + ", ".join(duplicate_serials[:12]))

    batch_actions = Counter()
    for group in group_items:
        if group["batch_id"] in existing_batches:
            batch_actions["update"] += 1
        else:
            batch_actions["insert"] += 1

    return {
        "batch_code": batch_code,
        "line_id": line_id,
        "line": line,
        "line_region": line_region,
        "source_rows": source_rows,
        "blank_serials": blank_serials,
        "serials": serials,
        "groups": group_items,
        "existing_batches": existing_batches,
        "existing_units": existing_units,
        "active_foreign_batches": active_foreign,
        "conflicts": conflicts,
        "unit_actions": unit_actions,
        "batch_actions": batch_actions,
        "placeholder": False,
    }


def print_plan(plan: dict[str, Any]) -> None:
    print("\nAssignment plan:")
    print(f"  batch_code: {plan['batch_code']}")
    print(f"  target line: {plan['line_id']} ({clean(plan['line'].get('line_name'))}) region={region_label(plan['line_region'])}")
    print(f"  source rows: {len(plan['source_rows'])}, usable serials: {len(plan['serials'])}, blank serials skipped: {len(plan['blank_serials'])}")
    statuses = Counter(clean(row.get("fg_status")) or "-" for row in plan["source_rows"])
    if statuses:
        print("  source statuses: " + ", ".join(f"{status}={count}" for status, count in sorted(statuses.items())))
    elif plan.get("placeholder"):
        print("  source statuses: (no source rows; external placeholder batch)")
    print("  V8 batch groups:")
    for group in plan["groups"]:
        print(
            f"    - {group['batch_id']} category={group['major']} family={group['family']} "
            f"region={region_label(group['region'])} units={len(group['rows'])} capacity={group['capacity']}"
        )
    print(
        "  batch records: "
        f"insert={plan['batch_actions'].get('insert', 0)} update={plan['batch_actions'].get('update', 0)}"
    )
    print(
        "  unit records: "
        f"insert={plan['unit_actions'].get('insert', 0)} "
        f"update={plan['unit_actions'].get('update', 0)} "
        f"reassign={plan['unit_actions'].get('reassign', 0)} "
        f"unchanged={plan['unit_actions'].get('unchanged', 0)}"
    )
    if plan["conflicts"]:
        print("\nConflicts:")
        for item in plan["conflicts"]:
            print(f"  - {item}")


def insert_row(cur, table: str, values: dict[str, Any]) -> None:
    cols = list(values.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO {qident(table)} ({', '.join(qident(c) for c in cols)}) VALUES ({placeholders})"
    cur.execute(sql, [values[c] for c in cols])


def update_row(cur, table: str, key_col: str, key_value: Any, values: dict[str, Any]) -> int:
    cols = list(values.keys())
    if not cols:
        return 0
    sql = f"UPDATE {qident(table)} SET {', '.join(qident(c) + ' = %s' for c in cols)} WHERE {qident(key_col)} = %s"
    cur.execute(sql, [values[c] for c in cols] + [key_value])
    return int(cur.rowcount or 0)


def minmax_due(rows: list[dict[str, Any]]) -> tuple[Any, Any]:
    due_values = [date_only(row.get("due_dt")) for row in rows if date_only(row.get("due_dt"))]
    if not due_values:
        return None, None
    return min(due_values), max(due_values)


def ensure_batch(cur, group: dict[str, Any], plan: dict[str, Any], stats: Counter) -> None:
    cols = table_columns(cur, "batches")
    existing = plan["existing_batches"].get(group["batch_id"])
    due_min, due_max = minmax_due(group["rows"])
    snapshot = json.dumps(
        {
            "source": "finished_goods_data",
            "manual_tool": "assign_fg_batch_to_kanban_line",
            "batch_code": plan["batch_code"],
            "category": group["major"],
            "region": group["region"],
            "unit_count": len(group["rows"]),
        },
        ensure_ascii=False,
        default=json_default,
    )
    values: dict[str, Any] = {
        "batch_no": group["batch_no"],
        "batch_code": plan["batch_code"],
        "model_type": group["family"],
        "capacity": group["capacity"],
        "status": "In_Production",
        "due_date_start": due_min,
        "due_date_end": due_max,
        "expected_inbound_date": due_min,
        "capacity_snapshot": snapshot,
        "source": "manual_fg_batch_line",
        "production_line_id": plan["line_id"],
        "updated_at": datetime.now(),
    }
    if "major_category" in cols:
        values["major_category"] = group["major"]
    if "base_capacity" in cols:
        values["base_capacity"] = group["default_capacity"]
    if "capacity_override" in cols:
        values["capacity_override"] = None

    if existing:
        update_values = {k: v for k, v in values.items() if k in cols}
        old_capacity = int(existing.get("capacity") or 0)
        if old_capacity > group["capacity"] and "capacity" in update_values:
            update_values["capacity"] = old_capacity
        update_row(cur, "batches", "batch_id", group["batch_id"], update_values)
        stats["batches_updated"] += 1
    else:
        insert_values = {"batch_id": group["batch_id"], **values, "created_at": datetime.now()}
        insert_values = {k: v for k, v in insert_values.items() if k in cols}
        insert_row(cur, "batches", insert_values)
        stats["batches_inserted"] += 1


def max_slots(cur, batch_ids: list[str]) -> dict[str, int]:
    if not batch_ids:
        return {}
    placeholders = ",".join(["%s"] * len(batch_ids))
    cur.execute(
        f"SELECT batch_id, COALESCE(MAX(slot_index), 0) AS max_slot FROM units WHERE batch_id IN ({placeholders}) GROUP BY batch_id",
        batch_ids,
    )
    out = {bid: 0 for bid in batch_ids}
    for row in cur.fetchall():
        out[row["batch_id"]] = int(row.get("max_slot") or 0)
    return out


def next_slot(slot_next: dict[str, int], batch_id: str) -> int:
    slot_next[batch_id] = int(slot_next.get(batch_id, 0)) + 1
    return slot_next[batch_id]


def unit_values(row: dict[str, Any], group: dict[str, Any], plan: dict[str, Any], slot: int, unit_id: str) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "serial_no": clean(row.get("serial_no")),
        "forecast_serial_no": None,
        "batch_id": group["batch_id"],
        "slot_index": slot,
        "model_type": clean(row.get("model")) or group["family"],
        "production_line_id": plan["line_id"],
        "status": "In_Production",
        "contract_no": none_if_blank(row.get("contract_no")),
        "customer": none_if_blank(row.get("customer")),
        "dealer_id": None,
        "dealer_name": none_if_blank(row.get("dealer")),
        "due_date": date_only(row.get("due_dt")),
        "sales_id": none_if_blank(row.get("order_no")),
        "order_remark": none_if_blank(row.get("remark")),
        "is_locked": 0,
        "is_contract_pinned": 0,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


def ensure_units(cur, plan: dict[str, Any], stats: Counter) -> list[str]:
    cols = table_columns(cur, "units")
    existing_units = plan["existing_units"]
    slot_next = max_slots(cur, [g["batch_id"] for g in plan["groups"]])
    selected_unit_ids = []
    old_lines = set()
    old_batches = set()

    for group in plan["groups"]:
        for row in group["rows"]:
            serial = clean(row.get("serial_no"))
            existing_list = existing_units.get(serial, [])
            existing = existing_list[0] if len(existing_list) == 1 else None
            if existing:
                unit_id = existing["unit_id"]
                old_line = clean(existing.get("production_line_id"))
                old_batch = clean(existing.get("batch_id"))
                old_slot = int(existing.get("slot_index") or 0)
                if old_batch and old_batch != group["batch_id"]:
                    old_batches.add(old_batch)
                slot = old_slot if old_batch == group["batch_id"] and old_slot > 0 else next_slot(slot_next, group["batch_id"])
                values = unit_values(row, group, plan, slot, unit_id)
                update_values = {k: v for k, v in values.items() if k in cols and k not in ("unit_id", "created_at")}
                update_row(cur, "units", "unit_id", unit_id, update_values)
                if old_line and old_line != plan["line_id"]:
                    old_lines.add(old_line)
                if old_batch != group["batch_id"] or old_line != plan["line_id"]:
                    stats["units_reassigned"] += 1
                else:
                    stats["units_updated"] += 1
                selected_unit_ids.append(unit_id)
                continue

            unit_id = unit_id_for(serial, group["batch_id"])
            cur.execute("SELECT unit_id, serial_no, forecast_serial_no FROM units WHERE unit_id = %s", (unit_id,))
            collision = cur.fetchone()
            if collision:
                unit_id = unit_id_for(serial + "|" + digest(str(datetime.now())), group["batch_id"])
            slot = next_slot(slot_next, group["batch_id"])
            values = unit_values(row, group, plan, slot, unit_id)
            insert_values = {k: v for k, v in values.items() if k in cols}
            insert_row(cur, "units", insert_values)
            stats["units_inserted"] += 1
            selected_unit_ids.append(unit_id)

    stats["_old_lines"] = list(old_lines)  # type: ignore[index]
    stats["_old_batches"] = list(old_batches)  # type: ignore[index]
    return selected_unit_ids


def ensure_ledgers(cur, unit_ids: list[str], plan: dict[str, Any], stats: Counter) -> None:
    for unit_id in unit_ids:
        cur.execute(
            """
            SELECT id, production_line_id, batch_code
            FROM production_history_ledger
            WHERE unit_id = %s AND status = 'In_Production'
            ORDER BY id
            """,
            (unit_id,),
        )
        active = list(cur.fetchall())
        good = [
            row
            for row in active
            if clean(row.get("production_line_id")) == plan["line_id"]
            and clean(row.get("batch_code")) == plan["batch_code"]
        ]
        if len(active) == 1 and len(good) == 1:
            cur.execute(
                """
                UPDATE production_history_ledger phl
                JOIN units u ON u.unit_id = phl.unit_id
                LEFT JOIN production_lines pl ON pl.line_id = u.production_line_id
                LEFT JOIN batches b ON b.batch_id = u.batch_id
                SET phl.production_line_id = u.production_line_id,
                    phl.production_line_name = pl.line_name,
                    phl.batch_code = COALESCE(b.batch_code, CONCAT('batch-', b.batch_no)),
                    phl.model_type = u.model_type,
                    phl.contract_no = u.contract_no,
                    phl.customer = u.customer,
                    phl.dealer_name = u.dealer_name,
                    phl.order_remark = u.order_remark,
                    phl.updated_at = NOW()
                WHERE phl.id = %s
                """,
                (good[0]["id"],),
            )
            stats["ledgers_kept"] += 1
            continue

        if active:
            cur.execute(
                """
                UPDATE production_history_ledger
                SET status = 'Cancelled', completed_at = NOW(), updated_at = NOW()
                WHERE unit_id = %s AND status = 'In_Production'
                """,
                (unit_id,),
            )
            stats["ledgers_cancelled"] += int(cur.rowcount or 0)

        cur.execute(
            """
            INSERT INTO production_history_ledger (
                unit_id, production_line_id, production_line_name, batch_code,
                model_type, contract_no, customer, dealer_name, order_remark,
                status, scheduled_at
            )
            SELECT
                u.unit_id,
                u.production_line_id,
                pl.line_name,
                COALESCE(b.batch_code, CONCAT('batch-', b.batch_no)),
                u.model_type,
                u.contract_no,
                u.customer,
                u.dealer_name,
                u.order_remark,
                'In_Production',
                NOW()
            FROM units u
            LEFT JOIN production_lines pl ON pl.line_id = u.production_line_id
            LEFT JOIN batches b ON b.batch_id = u.batch_id
            WHERE u.unit_id = %s
            """,
            (unit_id,),
        )
        stats["ledgers_inserted"] += int(cur.rowcount or 0)


def sync_target_line(cur, plan: dict[str, Any], stats: Counter, replace_line: bool = False) -> None:
    first_batch_id = plan["groups"][0]["batch_id"] if plan["groups"] else None
    current = clean(plan["line"].get("current_batch_id"))
    if current and plan["active_foreign_batches"] and not replace_line:
        cur.execute("UPDATE production_lines SET status = 'Busy', updated_at = NOW() WHERE line_id = %s", (plan["line_id"],))
    else:
        cur.execute(
            "UPDATE production_lines SET status = 'Busy', current_batch_id = %s, updated_at = NOW() WHERE line_id = %s",
            (first_batch_id, plan["line_id"]),
        )
    stats["lines_updated"] += int(cur.rowcount or 0)


def replace_target_line_foreign_batches(cur, plan: dict[str, Any], target_batch_ids: list[str], stats: Counter) -> None:
    if not target_batch_ids:
        return
    placeholders = ",".join(["%s"] * len(target_batch_ids))
    cur.execute(
        f"""
        SELECT batch_id
        FROM batches
        WHERE production_line_id = %s
          AND status = 'In_Production'
          AND batch_id NOT IN ({placeholders})
        """,
        [plan["line_id"]] + target_batch_ids,
    )
    foreign_batch_ids = [row["batch_id"] for row in cur.fetchall()]
    if not foreign_batch_ids:
        return

    batch_placeholders = ",".join(["%s"] * len(foreign_batch_ids))
    cur.execute(
        f"""
        SELECT unit_id
        FROM units
        WHERE batch_id IN ({batch_placeholders})
          AND status = 'In_Production'
        """,
        foreign_batch_ids,
    )
    unit_ids = [row["unit_id"] for row in cur.fetchall()]

    if unit_ids:
        unit_placeholders = ",".join(["%s"] * len(unit_ids))
        cur.execute(
            f"""
            UPDATE production_history_ledger
            SET status = 'Cancelled', completed_at = NOW(), updated_at = NOW()
            WHERE status = 'In_Production'
              AND unit_id IN ({unit_placeholders})
            """,
            unit_ids,
        )
        stats["replace_ledgers_cancelled"] += int(cur.rowcount or 0)

    cur.execute(
        f"""
        UPDATE units
        SET status = 'Pending', production_line_id = NULL, updated_at = NOW()
        WHERE batch_id IN ({batch_placeholders})
          AND status = 'In_Production'
        """,
        foreign_batch_ids,
    )
    stats["replace_units_pending"] += int(cur.rowcount or 0)

    cur.execute(
        f"""
        UPDATE batches
        SET status = 'Confirmed', production_line_id = NULL, updated_at = NOW()
        WHERE batch_id IN ({batch_placeholders})
          AND status = 'In_Production'
        """,
        foreign_batch_ids,
    )
    stats["replace_batches_detached"] += int(cur.rowcount or 0)


def cleanup_old_batches(cur, old_batch_ids: list[str], target_batch_ids: list[str], stats: Counter) -> None:
    target_set = set(target_batch_ids)
    for batch_id in old_batch_ids:
        if not batch_id or batch_id in target_set:
            continue
        cur.execute(
            "SELECT batch_id, status, production_line_id FROM batches WHERE batch_id = %s",
            (batch_id,),
        )
        batch = cur.fetchone()
        if not batch or clean(batch.get("status")) != "In_Production":
            continue
        old_line = clean(batch.get("production_line_id"))
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM units WHERE batch_id = %s AND status = 'In_Production'",
            (batch_id,),
        )
        active_units = int(cur.fetchone()["cnt"] or 0)
        if active_units > 0:
            continue

        cur.execute(
            """
            UPDATE batches
            SET status = 'Confirmed', production_line_id = NULL, updated_at = NOW()
            WHERE batch_id = %s AND status = 'In_Production'
            """,
            (batch_id,),
        )
        stats["old_batches_detached"] += int(cur.rowcount or 0)

        if old_line:
            cur.execute(
                """
                SELECT batch_id
                FROM batches
                WHERE production_line_id = %s AND status = 'In_Production'
                ORDER BY COALESCE(batch_code, ''), batch_no, batch_id
                LIMIT 1
                """,
                (old_line,),
            )
            next_batch = cur.fetchone()
            if next_batch:
                cur.execute(
                    "UPDATE production_lines SET status = 'Busy', current_batch_id = %s, updated_at = NOW() WHERE line_id = %s",
                    (next_batch["batch_id"], old_line),
                )
            else:
                cur.execute(
                    "UPDATE production_lines SET status = 'Idle', current_batch_id = NULL, updated_at = NOW() WHERE line_id = %s",
                    (old_line,),
                )
            stats["old_lines_refreshed"] += int(cur.rowcount or 0)


def cleanup_old_lines(cur, old_lines: list[str], stats: Counter) -> None:
    for line_id in old_lines:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM units WHERE production_line_id = %s AND status = 'In_Production'",
            (line_id,),
        )
        active_units = int(cur.fetchone()["cnt"] or 0)
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM batches WHERE production_line_id = %s AND status = 'In_Production'",
            (line_id,),
        )
        active_batches = int(cur.fetchone()["cnt"] or 0)
        if active_units == 0 and active_batches == 0:
            cur.execute(
                "UPDATE production_lines SET status = 'Idle', current_batch_id = NULL, updated_at = NOW() WHERE line_id = %s",
                (line_id,),
            )
            stats["old_lines_idled"] += int(cur.rowcount or 0)


def sync_factory_plan(cur, plan: dict[str, Any], stats: Counter) -> None:
    if not table_exists(cur, "factory_plan"):
        return
    cols = table_columns(cur, "factory_plan")
    if not {FG_CONTRACT, FG_MODEL, FP_STATUS}.issubset(cols):
        return
    pairs = set()
    for group in plan["groups"]:
        for row in group["rows"]:
            contract = clean(row.get("contract_no"))
            model = clean(row.get("model"))
            if contract and model:
                pairs.add((contract, model))
    for contract, model in pairs:
        cur.execute(
            f"""
            UPDATE factory_plan
            SET {qident(FP_STATUS)} = %s
            WHERE {qident(FG_CONTRACT)} = %s
              AND {qident(FG_MODEL)} COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci
              AND {qident(FP_STATUS)} = %s
            """,
            (FP_PLANNED, contract, model, FP_PENDING),
        )
        stats["factory_plan_pairs"] += 1
        stats["factory_plan_rows"] += int(cur.rowcount or 0)


def write_operation_log(cur, args: argparse.Namespace, plan: dict[str, Any], stats: Counter) -> None:
    if not table_exists(cur, "operation_log"):
        return
    cols = table_columns(cur, "operation_log")
    required = {"actor", "action", "target_type", "target_id", "detail", "created_at"}
    if not required.issubset(cols):
        return
    detail = json.dumps(
        {
            "batch_code": plan["batch_code"],
            "line_id": plan["line_id"],
            "groups": [{"batch_id": g["batch_id"], "category": g["major"], "units": len(g["rows"])} for g in plan["groups"]],
            "stats": {k: v for k, v in stats.items() if not k.startswith("_")},
        },
        ensure_ascii=False,
        default=json_default,
    )
    cur.execute(
        """
        INSERT INTO operation_log (actor, action, target_type, target_id, detail, created_at)
        VALUES (%s, 'manual_fg_batch_to_line', 'production_line', %s, %s, NOW())
        """,
        (args.actor, plan["line_id"], detail),
    )
    stats["operation_log_rows"] += int(cur.rowcount or 0)


def apply_plan(conn, plan: dict[str, Any], args: argparse.Namespace) -> Counter:
    stats: Counter = Counter()
    conn.autocommit(False)
    try:
        with conn.cursor() as cur:
            for group in plan["groups"]:
                ensure_batch(cur, group, plan, stats)
            unit_ids = ensure_units(cur, plan, stats)
            ensure_ledgers(cur, unit_ids, plan, stats)
            if args.replace_line:
                replace_target_line_foreign_batches(cur, plan, [g["batch_id"] for g in plan["groups"]], stats)
            sync_target_line(cur, plan, stats, replace_line=args.replace_line)
            cleanup_old_batches(cur, stats.get("_old_batches", []), [g["batch_id"] for g in plan["groups"]], stats)
            cleanup_old_lines(cur, stats.get("_old_lines", []), stats)
            sync_factory_plan(cur, plan, stats)
            write_operation_log(cur, args, plan, stats)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit(True)
    return stats


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assign a finished_goods_data batch to a V8 kanban production line.")
    parser.add_argument("--database", default="rjfinshed")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="030705")
    parser.add_argument("--batch-code", default="")
    parser.add_argument("--line-id", default="")
    parser.add_argument("--actor", default="manual_batch_line_tool")
    parser.add_argument("--list-limit", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reassign-existing", action="store_true")
    parser.add_argument("--reopen-completed", action="store_true")
    parser.add_argument("--replace-line", action="store_true")
    parser.add_argument("--all-statuses", action="store_true")
    parser.add_argument("--include-shipped", action="store_true")
    parser.add_argument("--allow-empty-batch", action="store_true")
    parser.add_argument("--ensure-default-lines", action="store_true")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    prompted = False
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            require_tables(cur, ["finished_goods_data", "production_lines", "batches", "units", "production_history_ledger"])
            if args.ensure_default_lines:
                created = ensure_default_lines(cur, args.dry_run)
                if created:
                    print(f"default production lines created/planned: {created}")

            if args.list_only:
                print_batches(fetch_batch_summaries(cur, args.list_limit))
                print_lines(fetch_lines(cur))
                return 0

            if not clean(args.batch_code):
                prompted = True
            batch_code = choose_batch(cur, args.batch_code, args.list_limit)
            if not clean(args.line_id):
                prompted = True
            line_id = choose_line(cur, args.line_id)

            plan = build_plan(cur, args, batch_code, line_id)
            print_plan(plan)
            if plan["conflicts"]:
                return 2
            if args.dry_run:
                print("\nDRY RUN: no database changes were committed.")
                return 0

            if prompted and not args.yes:
                answer = input("\nType YES to write this assignment: ").strip()
                if answer != "YES":
                    print("cancelled")
                    return 1

        stats = apply_plan(conn, plan, args)
        clean_stats = {k: v for k, v in stats.items() if not str(k).startswith("_")}
        print("\nAssignment complete:")
        print(json.dumps(clean_stats, ensure_ascii=False, default=json_default, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
