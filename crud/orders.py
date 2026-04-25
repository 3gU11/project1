from datetime import datetime
from functools import lru_cache
import json
import uuid

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from crud.inventory import get_data, save_data
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
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM sales_orders"))
            if not df.empty:
                df[ORDER_COLS].to_sql('sales_orders', conn, if_exists='append', index=False, method='multi', chunksize=500)
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"订单保存失败: {e}") from e


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


def allocate_inventory(order_id, customer, agent, selected_sns, operator=None):
    df = get_data()
    orders = get_orders()
    order_note = ""
    target_order = orders[orders['订单号'] == order_id]
    if not target_order.empty:
        order_note = str(target_order.iloc[0]['备注'])

    current_status_df = df[df['流水号'].isin(selected_sns)]
    pending_inbound_sns = current_status_df[current_status_df['状态'] == '待入库']['流水号'].tolist()
    if pending_inbound_sns:
        append_log("直接配货-自动入库", pending_inbound_sns, operator=operator)

    mask = df['流水号'].isin(selected_sns)
    df.loc[mask, '状态'] = '待发货'
    df.loc[mask, '占用订单号'] = order_id
    df.loc[mask, '客户'] = customer
    df.loc[mask, '代理商'] = agent
    df.loc[mask, '订单备注'] = order_note
    df.loc[mask, '更新时间'] = datetime.now()

    save_data(df)
    append_log(f"配货锁定-{order_id}", selected_sns, operator=operator)


def revert_to_inbound(selected_sns, reason="撤回操作", operator=None):
    df = get_data()
    mask = df['流水号'].isin(selected_sns)
    df.loc[mask, '状态'] = '待入库'
    df.loc[mask, '占用订单号'] = ""
    df.loc[mask, '客户'] = ""
    df.loc[mask, '代理商'] = ""
    df.loc[mask, '订单备注'] = ""
    df.loc[mask, '更新时间'] = datetime.now()
    save_data(df)
    append_log(f"{reason}-退回待入库", selected_sns, operator=operator)


def update_sales_order(order_id, new_data, force_unbind=False):
    df = get_data()
    mask_alloc = (df['占用订单号'] == order_id) & (df['状态'] != '已出库')
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
