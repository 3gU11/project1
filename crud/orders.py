from datetime import datetime
from functools import lru_cache
import json
import uuid

import pandas as pd
from sqlalchemy import text, bindparam
from sqlalchemy.exc import OperationalError

from crud.inventory import clear_inventory_data_caches, get_data
from crud.cloud_sync_outbox import enqueue_wechat_batch_summary_sync
from crud.inbound_history import notify_inbound_completion, record_inbound_history
from crud.logs import append_log
from database import get_engine
from utils.cache import fetch_data_with_cache
from utils.local_cache import ttl_cache
from utils.parsers import parse_plan_map


ORDER_COLS = ["订单号", "客户名", "代理商", "需求机型", "需求数量", "下单时间", "备注", "包装选项", "发货时间", "指定批次/来源", "status", "delete_reason"]


def _to_int_qty(value):
    try:
        return int(float(value))
    except Exception:
        return 0


def _normalize_source_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    if value is None:
        return {}
    raw = str(value).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            return {"note": parsed}
        return {"note": raw}
    except Exception:
        pass
    legacy_plan = parse_plan_map(raw)
    if legacy_plan:
        return legacy_plan
    return {"note": raw}


@lru_cache(maxsize=1)
def get_orders():
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT * FROM sales_orders", conn)
        if df.empty:
            return pd.DataFrame(columns=ORDER_COLS)
        for col in ORDER_COLS:
            if col not in df.columns:
                if col == "需求数量":
                    df[col] = 0
                elif col == "指定批次/来源":
                    df[col] = {}
                else:
                    df[col] = ""
        df["需求数量"] = pd.to_numeric(df["需求数量"], errors="coerce").fillna(0).astype(int)
        for dt_col in ["下单时间", "发货时间"]:
            if dt_col in df.columns:
                df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        df["指定批次/来源"] = df["指定批次/来源"].apply(_normalize_source_json)
        fill_cols = [c for c in ORDER_COLS if c not in ["需求数量", "下单时间", "发货时间", "指定批次/来源"]]
        for col in fill_cols:
            df[col] = df[col].fillna("")
        df["订单号"] = df["订单号"].astype(str).str.strip()
        df = df[df["订单号"] != ""].copy()
        df = df.drop_duplicates(subset=["订单号"], keep="last")
        mask = (df['status'] == "") | (df['status'].isna())
        if mask.any():
            df.loc[mask, 'status'] = "active"
        return df
    except (OperationalError, Exception):
        return pd.DataFrame(columns=ORDER_COLS)


@ttl_cache(ttl_seconds=30)
def get_orders_v2():
    """
    优化版：使用 TTL 缓存替代 lru_cache(maxsize=1)
    缓存 30 秒后自动过期，避免脏数据
    """
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT * FROM sales_orders", conn)
        if df.empty:
            return pd.DataFrame(columns=ORDER_COLS)
        for col in ORDER_COLS:
            if col not in df.columns:
                if col == "需求数量":
                    df[col] = 0
                elif col == "指定批次/来源":
                    df[col] = {}
                else:
                    df[col] = ""
        df["需求数量"] = pd.to_numeric(df["需求数量"], errors="coerce").fillna(0).astype(int)
        for dt_col in ["下单时间", "发货时间"]:
            if dt_col in df.columns:
                df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        df["指定批次/来源"] = df["指定批次/来源"].apply(_normalize_source_json)
        fill_cols = [c for c in ORDER_COLS if c not in ["需求数量", "下单时间", "发货时间", "指定批次/来源"]]
        for col in fill_cols:
            df[col] = df[col].fillna("")
        df["订单号"] = df["订单号"].astype(str).str.strip()
        df = df[df["订单号"] != ""].copy()
        df = df.drop_duplicates(subset=["订单号"], keep="last")
        mask = (df['status'] == "") | (df['status'].isna())
        if mask.any():
            df.loc[mask, 'status'] = "active"
        return df
    except (OperationalError, Exception):
        return pd.DataFrame(columns=ORDER_COLS)


def save_orders(df):
    get_orders.cache_clear()
    get_orders_v2.cache_clear()  # 同时清除 v2 版本缓存
    try:
        df = df.copy()
        for col in ORDER_COLS:
            if col not in df.columns:
                if col == "需求数量":
                    df[col] = 0
                elif col == "指定批次/来源":
                    df[col] = {}
                else:
                    df[col] = ""
        df["需求数量"] = pd.to_numeric(df["需求数量"], errors="coerce").fillna(0).astype(int)
        for dt_col in ["下单时间", "发货时间"]:
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
        df["指定批次/来源"] = df["指定批次/来源"].apply(
            lambda v: json.dumps(_normalize_source_json(v), ensure_ascii=False)
        )
        fill_cols = [c for c in ORDER_COLS if c not in ["需求数量", "下单时间", "发货时间", "指定批次/来源"]]
        for col in fill_cols:
            df[col] = df[col].fillna("")
        df["订单号"] = df["订单号"].astype(str).str.strip()
        df = df[df["订单号"] != ""].copy()
        df = df.drop_duplicates(subset=["订单号"], keep="last")
        with get_engine().begin() as conn:
            if not df.empty:
                tmp_table = f"tmp_sales_orders_save_{uuid.uuid4().hex}"
                try:
                    df[ORDER_COLS].to_sql(tmp_table, conn, if_exists='replace', index=False, method='multi', chunksize=500)
                    cols_sql = ", ".join(f"`{col}`" for col in ORDER_COLS)
                    select_sql = ", ".join(f"t.`{col}`" for col in ORDER_COLS)
                    update_assignments = []
                    for col in ORDER_COLS:
                        if col == "订单号":
                            continue
                        if col == "下单时间":
                            update_assignments.append(
                                "so.`下单时间` = CASE "
                                "WHEN t.`下单时间` IS NOT NULL "
                                "AND so.`下单时间` IS NOT NULL "
                                "AND TIME(t.`下单时间`) = '00:00:00' "
                                "AND DATE(t.`下单时间`) = DATE(so.`下单时间`) "
                                "THEN so.`下单时间` ELSE t.`下单时间` END"
                            )
                        else:
                            update_assignments.append(f"so.`{col}` = t.`{col}`")
                    update_sql = ", ".join(update_assignments)
                    upsert_sql = ", ".join(f"`{col}`=VALUES(`{col}`)" for col in ORDER_COLS if col != "订单号")
                    conn.execute(text(f"""
                        UPDATE sales_orders so
                        INNER JOIN `{tmp_table}` t ON so.`订单号` = t.`订单号`
                        SET {update_sql}
                    """))
                    conn.execute(text(f"""
                        INSERT INTO sales_orders ({cols_sql})
                        SELECT {select_sql} FROM `{tmp_table}` t
                        WHERE NOT EXISTS (
                            SELECT 1 FROM sales_orders so WHERE so.`订单号` = t.`订单号`
                        )
                        ON DUPLICATE KEY UPDATE {upsert_sql}
                    """))
                finally:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{tmp_table}`"))
                    except Exception:
                        pass
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"订单保存失败: {e}") from e


def _normalize_order_note(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"none", "nan", "null"}:
        return ""
    return text


def _normalize_allocation_model(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("(加高)", "").replace("（加高）", "").strip()


def _is_high_model_hint(*values) -> bool:
    return any("加高" in str(value or "") for value in values)


def create_sales_order(customer, agent, model_data, note, pack_option="", delivery_time="", source_batch=""):
    get_orders.cache_clear()
    get_orders_v2.cache_clear()  # 同时清除 v2 版本缓存
    odf = get_orders()
    order_id = f"SO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
    final_model_str = ""
    total_qty = 0

    if isinstance(model_data, dict):
        parts = []
        for m, q in model_data.items():
            parts.append(f"{m}:{q}")
            total_qty += int(q)
        final_model_str = ";".join(parts)
    else:
        final_model_str = str(model_data)

    new_row = {
        "订单号": order_id,
        "客户名": customer,
        "代理商": agent,
        "需求机型": final_model_str,
        "需求数量": total_qty if isinstance(model_data, dict) else 0,
        "下单时间": datetime.now(),
        "备注": note,
        "包装选项": pack_option,
        "发货时间": pd.to_datetime(delivery_time, errors="coerce"),
        "指定批次/来源": _normalize_source_json(source_batch),
    }
    odf = pd.concat([odf, pd.DataFrame([new_row])], ignore_index=True)
    save_orders(odf)
    return order_id


def _build_model_note_map(order_id):
    """根据订单号从 factory_plan 构建逐台机型备注需求。"""
    from crud.planning import get_factory_plan_v2
    plan_df = get_factory_plan_v2()
    if plan_df.empty:
        return []
    matched = plan_df[plan_df['订单号'].astype(str).str.strip() == str(order_id).strip()]
    if matched.empty:
        return []
    order_context = {}
    try:
        orders = get_orders()
        order_hit = orders[orders['订单号'].astype(str).str.strip() == str(order_id).strip()]
        if not order_hit.empty:
            order_context = order_hit.iloc[0].to_dict()
    except Exception:
        order_context = {}
    try:
        from api.routes.planning import _split_factory_plan_detail_rows
        plan_rows = _split_factory_plan_detail_rows(matched.to_dict(orient="records"), order_context)
    except Exception:
        plan_rows = matched.to_dict(orient="records")
    note_map = []
    for row in plan_rows:
        model = str(row.get('机型', '')).strip()
        note = _normalize_order_note(row.get('备注', ''))
        qty = _to_int_qty(row.get('数量', row.get('排产数量', 0)))
        if qty <= 0:
            qty = 1
        if model:
            clean_model = _normalize_allocation_model(model)
            high = _is_high_model_hint(model, note)
            for _ in range(qty):
                note_map.append({
                    "model": clean_model,
                    "high": high,
                    "note": note,
                })
    return note_map


def _remaining_model_note_counts(model_note_map):
    counts = {}
    for item in model_note_map:
        key = (item["model"], bool(item["high"]), str(item.get("note") or ""))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _find_model_note(model_note_map, model, row_note=""):
    clean_model = _normalize_allocation_model(model)
    high = _is_high_model_hint(model, row_note)
    for item in model_note_map:
        if item["model"] == clean_model and item["high"] == high:
            return item["note"]
    for item in model_note_map:
        if item["model"] == clean_model:
            return item["note"]
    return ""


def allocate_inventory(order_id, customer, agent, selected_sns, operator=None):
    order_id = str(order_id or "").strip()
    serial_nos = list(dict.fromkeys(str(sn).strip() for sn in (selected_sns or []) if str(sn).strip()))
    if not serial_nos:
        return {"stock": 0, "production": 0}

    model_note_map = _build_model_note_map(order_id)
    remaining_note_counts = _remaining_model_note_counts(model_note_map)
    contract_candidates: dict[str, set[str]] = {}
    order_contract_ids: set[str] = set()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stock_sns: list[str] = []
    production_sns: list[str] = []

    try:
        with get_engine().begin() as conn:
            for contract_no, model in conn.execute(
                text("SELECT `合同号`, `机型` FROM factory_plan WHERE TRIM(COALESCE(`订单号`, '')) = :order_id"),
                {"order_id": order_id},
            ).fetchall():
                contract_no = str(contract_no or "").strip()
                model = str(model or "").strip()
                if contract_no and model:
                    contract_candidates.setdefault(model, set()).add(contract_no)
                    order_contract_ids.add(contract_no)

            active_units = conn.execute(text("""
                SELECT u.unit_id, COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
                       u.model_type, COALESCE(u.sales_id, '') AS sales_id,
                       COALESCE(u.contract_no, '') AS contract_no,
                       COALESCE(u.order_remark, '') AS order_remark,
                       COALESCE(u.is_locked, 0) AS is_locked, b.batch_code, b.expected_inbound_date
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                LEFT JOIN finished_goods_data fg
                  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
                WHERE b.status IN ('Confirmed', 'In_Production')
                  AND COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) IN :sns
                  AND (
                      fg.`流水号` IS NULL
                      OR (
                          TRIM(COALESCE(fg.`状态`, '')) NOT LIKE '库存中%'
                          AND TRIM(COALESCE(fg.`状态`, '')) NOT IN ('待发货', '已出库', '已发货', '报废')
                      )
                  )
                FOR UPDATE
            """).bindparams(bindparam("sns", expanding=True)), {"sns": serial_nos}).mappings().all()
            unit_by_sn = {str(row["serial_no"]).strip(): dict(row) for row in active_units}

            stock_rows = conn.execute(text("""
                SELECT `流水号` AS serial_no, `机型` AS model_type, COALESCE(`状态`, '') AS status,
                       COALESCE(`占用订单号`, '') AS sales_id, COALESCE(`合同号`, '') AS contract_no,
                       COALESCE(`合同备注`, '') AS order_remark, COALESCE(`批次号`, '') AS batch_code
                FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE
            """).bindparams(bindparam("sns", expanding=True)), {"sns": serial_nos}).mappings().all()
            stock_by_sn = {str(row["serial_no"]).strip(): dict(row) for row in stock_rows}

            missing = [sn for sn in serial_nos if sn not in unit_by_sn and sn not in stock_by_sn]
            if missing:
                raise ValueError(f"机台不存在: {', '.join(missing[:10])}")

            for sn in serial_nos:
                source_row = unit_by_sn.get(sn) or stock_by_sn.get(sn) or {}
                model = str(source_row.get("model_type") or "").strip()
                contracts = contract_candidates.get(model, set())
                contract_no = next(iter(contracts)) if len(contracts) == 1 else ""
                current_note = _normalize_order_note(source_row.get("order_remark", ""))
                clean_model = _normalize_allocation_model(model)
                high = _is_high_model_hint(model, current_note)
                note = current_note
                for key, count in remaining_note_counts.items():
                    if count > 0 and key[0] == clean_model and key[1] == high:
                        note = key[2]
                        remaining_note_counts[key] -= 1
                        break

                if sn in unit_by_sn:
                    row = unit_by_sn[sn]
                    occupied = str(row.get("sales_id") or "").strip()
                    if occupied not in ("", order_id):
                        raise ValueError(f"在产机台 {sn} 已被订单 {occupied} 占用")
                    if int(row.get("is_locked") or 0) and occupied != order_id:
                        raise ValueError(f"在产机台 {sn} 已锁定")
                    existing_contract = str(row.get("contract_no") or "").strip()
                    if existing_contract and existing_contract not in order_contract_ids:
                        raise ValueError(f"在产机台 {sn} 已绑定合同 {existing_contract}")
                    contract_no = existing_contract or contract_no
                    conn.execute(text("""
                        UPDATE units SET contract_no=:contract_no, sales_id=:order_id,
                            customer=:customer, dealer_name=:agent, order_remark=:note, updated_at=NOW()
                        WHERE unit_id=:unit_id
                    """), {"contract_no": contract_no or None, "order_id": order_id, "customer": customer,
                           "agent": agent, "note": note or None, "unit_id": row["unit_id"]})
                    inventory_values = {
                        "sn": sn, "batch": row.get("batch_code") or "", "model": model,
                        "eta": row.get("expected_inbound_date"), "now": now_str, "order_id": order_id,
                        "customer": customer, "agent": agent, "note": note or None,
                        "contract_no": contract_no or None,
                    }
                    update_result = conn.execute(text("""
                        UPDATE finished_goods_data
                        SET `占用订单号`=:order_id, `客户`=:customer, `代理商`=:agent,
                            `合同备注`=:note, `合同号`=:contract_no, `状态`='待发货',
                            `批次号`=:batch, `机型`=:model, `预计入库时间`=:eta, `更新时间`=:now
                        WHERE TRIM(`流水号`) = :sn
                    """), inventory_values)
                    if update_result.rowcount == 0:
                        conn.execute(text("""
                            INSERT INTO finished_goods_data
                                (`流水号`,`批次号`,`机型`,`状态`,`预计入库时间`,`更新时间`,`占用订单号`,`客户`,`代理商`,`合同备注`,`合同号`)
                            VALUES (:sn,:batch,:model,'待发货',:eta,:now,:order_id,:customer,:agent,:note,:contract_no)
                        """), inventory_values)
                    production_sns.append(sn)
                    continue

                row = stock_by_sn[sn]
                status = str(row.get("status") or "").strip()
                occupied = str(row.get("sales_id") or "").strip()
                if not status.startswith("库存中"):
                    raise ValueError(f"机台 {sn} 不是可用库存现货（当前状态：{status or '空'}）")
                if occupied not in ("", order_id):
                    raise ValueError(f"库存机台 {sn} 已被订单 {occupied} 占用")
                conn.execute(text("""
                    UPDATE finished_goods_data SET `状态`='待发货', `占用订单号`=:order_id,
                        `客户`=:customer, `代理商`=:agent, `合同号`=:contract_no,
                        `合同备注`=:note, `更新时间`=:now WHERE `流水号`=:sn
                """), {"order_id": order_id, "customer": customer, "agent": agent,
                       "contract_no": contract_no or row.get("contract_no") or None,
                       "note": note or None, "now": now_str, "sn": sn})
                stock_sns.append(sn)
    except Exception as e:
        raise RuntimeError(f"配货写入失败: {e}") from e

    clear_inventory_data_caches()
    enqueue_wechat_batch_summary_sync("orders_allocate_inventory")
    if stock_sns:
        append_log(f"配货锁定-{order_id}-库存现货", stock_sns, operator=operator)
    if production_sns:
        append_log(f"配货锁定-{order_id}-在产预占", production_sns, operator=operator)
    return {"stock": len(stock_sns), "production": len(production_sns)}


def revert_to_inbound(selected_sns, reason="撤回操作", operator=None):
    serial_nos = list(dict.fromkeys(
        str(sn).strip() for sn in (selected_sns or []) if str(sn).strip()
    ))
    if not serial_nos:
        return

    sns_param = bindparam("sns", expanding=True)
    with get_engine().begin() as conn:
        active_rows = conn.execute(text("""
            SELECT COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no
            FROM units u JOIN batches b ON b.batch_id=u.batch_id
            WHERE b.status IN ('Confirmed','In_Production')
              AND COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) IN :sns
            FOR UPDATE
        """).bindparams(sns_param), {"sns": serial_nos}).mappings().all()
        production_sns = {str(row["serial_no"]).strip() for row in active_rows}
        conn.execute(
            text("""
                UPDATE finished_goods_data
                SET `状态` = CASE
                        WHEN `流水号` IN :production_sns THEN '待入库'
                        WHEN TRIM(COALESCE(`Location_Code`, '')) <> ''
                            THEN CONCAT('库存中（', TRIM(`Location_Code`), '）')
                        ELSE '待入库'
                    END,
                    `占用订单号` = NULL,
                    `客户` = '',
                    `代理商` = '',
                    `合同号` = '',
                    `更新时间` = NOW()
                WHERE `流水号` IN :sns
            """).bindparams(sns_param, bindparam("production_sns", expanding=True)),
            {"sns": serial_nos, "production_sns": list(production_sns) or ["__none__"]},
        )
        conn.execute(
            text("""
                UPDATE units
                SET contract_no = NULL,
                    customer = NULL,
                    dealer_name = NULL,
                    sales_id = NULL,
                    due_date = NULL,
                    is_locked = 0,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = NOW()
                WHERE serial_no IN :sns OR forecast_serial_no IN :sns
            """).bindparams(sns_param),
            {"sns": serial_nos},
        )

    clear_inventory_data_caches()
    enqueue_wechat_batch_summary_sync("orders_revert_to_inbound")
    append_log(f"{reason}-退回待入库", serial_nos, operator=operator)


def mark_allocated_order_ready_after_inbound(order_id: str) -> bool:
    order_id = str(order_id or "").strip()
    if not order_id:
        return False
    with get_engine().begin() as conn:
        status = conn.execute(
            text("SELECT `status` FROM sales_orders WHERE `订单号`=:order_id FOR UPDATE"),
            {"order_id": order_id},
        ).scalar()
        if str(status or "").strip() != "allocated":
            return False
        pending = int(conn.execute(text("""
            SELECT COUNT(*) FROM finished_goods_data
            WHERE TRIM(COALESCE(`占用订单号`, ''))=:order_id
              AND TRIM(COALESCE(`状态`, '')) <> '待发货'
              AND TRIM(COALESCE(`状态`, '')) <> '已出库'
        """), {"order_id": order_id}).scalar() or 0)
        if pending > 0:
            return False
        conn.execute(
            text("UPDATE sales_orders SET `status`='ready' WHERE `订单号`=:order_id"),
            {"order_id": order_id},
        )
    get_orders.cache_clear()
    return True


def update_sales_order(order_id, new_data, force_unbind=False):
    df = get_data()
    mask_alloc = (
        (df['占用订单号'] == order_id)
        & (df['状态'] != '已出库')
        & (df['状态'].astype(str).str.strip() != '报废')
    )
    sns_to_unbind = df.loc[mask_alloc, '流水号'].tolist()
    has_allocation = len(sns_to_unbind) > 0

    if has_allocation:
        if force_unbind:
            revert_to_inbound(sns_to_unbind, reason=f"订单修改-自动解绑-{order_id}")
        else:
            return False, f"⚠️ 警告：该订单已锁定 {len(sns_to_unbind)} 台库存。修改将导致配货失效，是否继续？"

    orders = get_orders()
    idx = orders[orders['订单号'] == order_id].index
    if not idx.empty:
        for col, val in new_data.items():
            if col in orders.columns:
                if col == "需求数量":
                    orders.loc[idx, col] = _to_int_qty(val)
                elif col in ["下单时间", "发货时间"]:
                    orders.loc[idx, col] = pd.to_datetime(val, errors="coerce")
                elif col == "指定批次/来源":
                    orders.loc[idx, col] = _normalize_source_json(val)
                else:
                    orders.loc[idx, col] = str(val)
        save_orders(orders)
        msg_extra = f"已解绑 {len(sns_to_unbind)} 台关联机器。" if (has_allocation and force_unbind) else ""
        return True, f"订单更新成功！{msg_extra}"
    return False, "订单未找到"


def get_active_orders_summary():
    """按状态和机型拉取未完结订单的基础信息（SQL下推聚合）"""
    query = """
        SELECT `订单号`, `需求机型`, `需求数量`, `status`, `下单时间`
        FROM sales_orders
        WHERE `status` NOT IN ('deleted', 'done')
    """
    return fetch_data_with_cache(query, ttl=30)
