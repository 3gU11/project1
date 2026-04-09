from datetime import datetime
from functools import lru_cache

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from database import get_engine
from utils.cache import fetch_data_with_cache
from utils.parsers import parse_alloc_dict, to_json_text


@lru_cache(maxsize=1)
def get_planning_records():
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT order_id, model, plan_info, updated_at FROM planning_records", conn)
        return df.fillna("")
    except (OperationalError, Exception):
        return pd.DataFrame(columns=["order_id", "model", "plan_info", "updated_at"])


def save_planning_record(order_id, model, plan_info):
    get_planning_records.cache_clear()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_engine().begin() as conn:
            result = conn.execute(
                text("SELECT 1 FROM planning_records WHERE order_id=:oid AND model=:m"),
                {"oid": str(order_id), "m": str(model)}
            )
            if result.fetchone():
                conn.execute(
                    text("UPDATE planning_records SET plan_info=:pi, updated_at=:ua WHERE order_id=:oid AND model=:m"),
                    {"pi": str(plan_info), "ua": current_time, "oid": str(order_id), "m": str(model)}
                )
            else:
                conn.execute(
                    text("INSERT INTO planning_records (order_id, model, plan_info, updated_at) VALUES (:oid, :m, :pi, :ua)"),
                    {"oid": str(order_id), "m": str(model), "pi": str(plan_info), "ua": current_time}
                )
    except (IntegrityError, OperationalError, Exception) as e:
        print(f"Error saving planning record: {e}")
        raise


@lru_cache(maxsize=1)
def get_factory_plan():
    cols = ["合同号", "机型", "排产数量", "要求交期", "状态", "备注", "客户名", "代理商", "指定批次/来源", "订单号"]
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT * FROM factory_plan", conn)
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        if "指定批次/来源" in df.columns:
            df["指定批次/来源"] = df["指定批次/来源"].apply(parse_alloc_dict)
        fill_cols = [c for c in cols if c != "指定批次/来源"]
        for col in fill_cols:
            df[col] = df[col].fillna("")
        return df.drop(columns=['id'], errors='ignore')
    except (OperationalError, Exception):
        return pd.DataFrame(columns=cols)


def save_factory_plan(df):
    get_factory_plan.cache_clear()
    cols = ["合同号", "机型", "排产数量", "要求交期", "状态", "备注", "客户名", "代理商", "指定批次/来源", "订单号"]
    try:
        df = df.copy()
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        df["指定批次/来源"] = df["指定批次/来源"].apply(lambda v: to_json_text(parse_alloc_dict(v)))
        df["订单号"] = df["订单号"].apply(lambda v: None if str(v).strip() == "" else str(v).strip())
        for col in [c for c in cols if c != "指定批次/来源"]:
            if col != "订单号":
                df[col] = df[col].fillna("")
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM factory_plan"))
            if not df.empty:
                df[cols].to_sql('factory_plan', conn, if_exists='append', index=False, method='multi', chunksize=500)
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"排产计划保存失败: {e}") from e

def get_plans_by_status(status: str):
    """获取指定状态的排产计划（SQL下推过滤）"""
    query = "SELECT * FROM factory_plan WHERE `状态` = :status"
    df = fetch_data_with_cache(query, params={"status": status}, ttl=30)
    
    if df.empty:
        return df
        
    if "指定批次/来源" in df.columns:
        df["指定批次/来源"] = df["指定批次/来源"].apply(parse_alloc_dict)
    
    fill_cols = [c for c in df.columns if c != "指定批次/来源"]
    for col in fill_cols:
        df[col] = df[col].fillna("")
        
    return df.drop(columns=['id'], errors='ignore')
