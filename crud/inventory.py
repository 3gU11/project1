import json
import logging
from copy import deepcopy
from datetime import datetime
from functools import lru_cache

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import get_engine
from crud.cloud_sync_outbox import enqueue_wechat_batch_summary_sync
from crud.inbound_history import notify_inbound_completion, record_inbound_history
from utils.cache import fetch_data_with_cache
from utils.local_cache import ttl_cache


logger = logging.getLogger(__name__)
INVENTORY_COLS = ["批次号", "机型", "流水号", "状态", "预计入库时间", "更新时间", "占用订单号", "客户", "代理商", "合同备注", "Location_Code", "合同号"]
IMPORT_COLS = ["流水号", "批次号", "机型", "状态", "预计入库时间", "客户", "代理商", "合同备注", "合同号", "订单号"]
WAREHOUSE_MAX_CAPACITY = 5
LARGE_WAREHOUSE_MAX_CAPACITY = 15
SCRAP_WAREHOUSE_MAX_CAPACITY = 5
UNLIMITED_WAREHOUSE_CAPACITY = float("inf")
OLD_FACTORY_SLOT_CODES = (
    "老厂一车间400",
    "老厂一车间600",
    "老厂一车间500",
    "老厂四车间二楼400",
    "老厂四车间一楼400",
    "老厂四车间一楼500",
    "老厂四车间一楼600",
)
OLD_FACTORY_SLOT_CODE_SET = {"".join(code.split()) for code in OLD_FACTORY_SLOT_CODES}
EMERGENCY_BUFFER_SLOT_CODES = (
    "新厂一楼小机床存放区",
    "新厂2楼仓库门口存放区",
)
UNLIMITED_SLOT_CODE_SET = {
    "".join(code.split())
    for code in (*OLD_FACTORY_SLOT_CODES, *EMERGENCY_BUFFER_SLOT_CODES)
}
REQUIRED_SLOT_CODES = tuple(
    [f"大机型区域{index:02d}" for index in range(1, 16)]
    + ["闲置区01", "闲置区02", "实验室区01"]
    + list(OLD_FACTORY_SLOT_CODES)
    + list(EMERGENCY_BUFFER_SLOT_CODES)
    + ["报废区01"]
)


def _normalize_slot_code(slot_code):
    return "".join(str(slot_code or "").split())


def canonical_slot_code(slot_code):
    return str(slot_code or "").strip()


def is_scrap_slot(slot_code):
    normalized = _normalize_slot_code(slot_code)
    return normalized.startswith("报废区") or normalized.startswith("整机报废区")


def is_unlimited_slot(slot_code):
    normalized = _normalize_slot_code(slot_code)
    return normalized in UNLIMITED_SLOT_CODE_SET or normalized.startswith("老厂")


def get_slot_capacity(slot_code):
    normalized = _normalize_slot_code(slot_code)
    if is_unlimited_slot(slot_code):
        return UNLIMITED_WAREHOUSE_CAPACITY
    if any(normalized.startswith(prefix) for prefix in ("大机型区域", "闲置区", "实验室区")):
        return LARGE_WAREHOUSE_MAX_CAPACITY
    if is_scrap_slot(slot_code):
        return SCRAP_WAREHOUSE_MAX_CAPACITY
    return WAREHOUSE_MAX_CAPACITY


def merge_required_warehouse_slots(slots):
    existing = [deepcopy(slot) for slot in (slots or []) if isinstance(slot, dict)]
    existing_codes = {
        _normalize_slot_code(slot.get("code"))
        for slot in existing
        if _normalize_slot_code(slot.get("code"))
    }
    missing_codes = [code for code in REQUIRED_SLOT_CODES if _normalize_slot_code(code) not in existing_codes]
    if not missing_codes:
        return existing

    max_bottom = max(
        (float(slot.get("y") or 0) + float(slot.get("h") or 160) for slot in existing),
        default=0,
    )
    base_y = max(20, max_bottom + 20)
    width, height, gap_x, gap_y, columns = 300, 160, 40, 40, 5
    used_ids = {str(slot.get("id") or "") for slot in existing}
    for index, code in enumerate(missing_codes):
        base_id = f"required-slot-{_normalize_slot_code(code)}"
        slot_id = base_id
        suffix = 2
        while slot_id in used_ids:
            slot_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(slot_id)
        existing.append({
            "id": slot_id,
            "code": code,
            "x": 20 + (index % columns) * (width + gap_x),
            "y": base_y + (index // columns) * (height + gap_y),
            "w": width,
            "h": height,
            "status": "正常",
        })
    return existing


def enrich_warehouse_layout(layout_json):
    enriched = deepcopy(layout_json) if isinstance(layout_json, dict) else {"slots": []}
    slots = enriched.get("slots")
    if not isinstance(slots, list):
        enriched["slots"] = []
        return enriched
    enriched["slots"] = []
    for raw_slot in slots:
        if not isinstance(raw_slot, dict):
            continue
        slot = deepcopy(raw_slot)
        capacity = get_slot_capacity(slot.get("code"))
        unlimited = capacity == UNLIMITED_WAREHOUSE_CAPACITY
        slot["capacity"] = None if unlimited else int(capacity)
        slot["unlimited"] = unlimited
        enriched["slots"].append(slot)
    return enriched


def sanitize_warehouse_layout(layout_json):
    sanitized = deepcopy(layout_json) if isinstance(layout_json, dict) else {"slots": []}
    slots = sanitized.get("slots")
    if not isinstance(slots, list):
        sanitized["slots"] = []
        return sanitized
    for slot in slots:
        if isinstance(slot, dict):
            slot.pop("capacity", None)
            slot.pop("unlimited", None)
    return sanitized


def _has_column(conn, table_name, column_name):
    try:
        result = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}` LIKE :column_name"), {"column_name": column_name})
        return result.fetchone() is not None
    except Exception:
        try:
            rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            cols = [str(row[1]) for row in rows]
            return column_name in cols
        except Exception:
            return False


def _ensure_plan_import_status_column(conn):
    if _has_column(conn, "plan_import", "状态"):
        return False
    try:
        conn.execute(text("ALTER TABLE plan_import ADD COLUMN 状态 VARCHAR(20) NOT NULL DEFAULT '待入库'"))
    except Exception:
        conn.execute(text("ALTER TABLE plan_import ADD COLUMN `状态` TEXT NOT NULL DEFAULT '待入库'"))
    logger.warning("plan_import 表缺少 状态 列，已自动补齐")
    return True


def _ensure_plan_import_trace_columns(conn):
    added = False
    for col_name, col_def in [
        ("客户", "VARCHAR(200) DEFAULT ''"),
        ("代理商", "VARCHAR(200) DEFAULT ''"),
        ("合同备注", "TEXT"),
        ("合同号", "VARCHAR(100) DEFAULT ''"),
        ("订单号", "VARCHAR(100) DEFAULT ''"),
    ]:
        if _has_column(conn, "plan_import", col_name):
            continue
        try:
            conn.execute(text(f"ALTER TABLE plan_import ADD COLUMN `{col_name}` {col_def}"))
        except Exception:
            conn.execute(text(f"ALTER TABLE plan_import ADD COLUMN `{col_name}` TEXT"))
        added = True
    return added


def _normalize_contract_note_columns(df):
    normalized = df.copy()
    if "合同备注" not in normalized.columns:
        normalized["合同备注"] = ""
    for legacy_col in ["备注", "订单备注", "机台备注/配置"]:
        if legacy_col in normalized.columns:
            missing = normalized["合同备注"].fillna("").astype(str).str.strip() == ""
            normalized.loc[missing, "合同备注"] = normalized.loc[missing, legacy_col].fillna("").astype(str)
    return normalized


def _ensure_finished_goods_contract_note_column(conn):
    if not _has_column(conn, "finished_goods_data", "合同备注"):
        conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `合同备注` TEXT AFTER `代理商`"))


def _normalize_import_df(df):
    normalized = df.copy()
    for col in IMPORT_COLS:
        if col not in normalized.columns:
            normalized[col] = "待入库" if col == "状态" else ""
    normalized["流水号"] = normalized["流水号"].astype(str).str.strip()
    normalized["状态"] = normalized["状态"].astype(str).str.strip()
    normalized.loc[normalized["状态"] == "", "状态"] = "待入库"
    if "预计入库时间" in normalized.columns:
        normalized["预计入库时间"] = pd.to_datetime(normalized["预计入库时间"], errors="coerce")
    normalized = normalized[normalized["流水号"] != ""]
    return normalized[IMPORT_COLS]


@lru_cache(maxsize=1)
def get_data():
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT * FROM finished_goods_data", conn)
        if df.empty:
            return pd.DataFrame(columns=INVENTORY_COLS)
        df = _normalize_contract_note_columns(df.fillna(""))
        for col in INVENTORY_COLS:
            if col not in df.columns:
                df[col] = ""
            
        if "预计入库时间" in df.columns:
            df["预计入库时间"] = pd.to_datetime(df["预计入库时间"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        if "更新时间" in df.columns:
            df["更新时间"] = pd.to_datetime(df["更新时间"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
            
        try:
            df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        except Exception:
            pass
        return df
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"数据读取失败: {e}") from e


@ttl_cache(ttl_seconds=30)
def get_data_v2():
    """
    优化版：使用 TTL 缓存替代 lru_cache(maxsize=1)
    缓存 30 秒后自动过期，避免脏数据
    """
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT * FROM finished_goods_data", conn)
        if df.empty:
            return pd.DataFrame(columns=INVENTORY_COLS)
        df = _normalize_contract_note_columns(df.fillna(""))
        for col in INVENTORY_COLS:
            if col not in df.columns:
                df[col] = ""

        if "预计入库时间" in df.columns:
            df["预计入库时间"] = pd.to_datetime(df["预计入库时间"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        if "更新时间" in df.columns:
            df["更新时间"] = pd.to_datetime(df["更新时间"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")

        try:
            df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        except Exception:
            pass
        return df
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"数据读取失败: {e}") from e


def clear_inventory_data_caches():
    """Invalidate both inventory readers regardless of the active feature flags."""
    get_data.cache_clear()
    get_data_v2.cache_clear()


def save_data(df):
    clear_inventory_data_caches()
    try:
        df = df.drop_duplicates(subset=['流水号'], keep='last')
        df = df.copy()
        for col in INVENTORY_COLS:
            if col not in df.columns:
                df[col] = ""
        for dt_col in ["预计入库时间", "更新时间"]:
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
        df["占用订单号"] = df["占用订单号"].apply(lambda v: None if str(v).strip() == "" else str(v).strip())
        fill_cols = [c for c in INVENTORY_COLS if c not in ["预计入库时间", "更新时间", "占用订单号"]]
        for col in fill_cols:
            df[col] = df[col].fillna("")
        with get_engine().begin() as conn:
            _ensure_finished_goods_contract_note_column(conn)
            result = conn.execute(text("SHOW COLUMNS FROM finished_goods_data LIKE 'Location_Code'"))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `Location_Code` VARCHAR(100) DEFAULT ''"))
            if not _has_column(conn, "finished_goods_data", "合同号"):
                conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `合同号` VARCHAR(100) DEFAULT ''"))
            conn.execute(text("DELETE FROM finished_goods_data"))
            if not df.empty:
                df[INVENTORY_COLS].to_sql('finished_goods_data', conn, if_exists='append', index=False, method='multi', chunksize=500)
        enqueue_wechat_batch_summary_sync("finished_goods_save")
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"保存失败: {e}") from e


def save_data_v2(df):
    """
    优化版 save_data：使用 UPSERT (INSERT ... ON DUPLICATE KEY UPDATE)
    通过批量执行 (executemany) 并处理 NaT/NaN 提升性能和稳定性
    """
    clear_inventory_data_caches()

    try:
        df = df.drop_duplicates(subset=['流水号'], keep='last')
        df = df.copy()
        for col in INVENTORY_COLS:
            if col not in df.columns:
                df[col] = ""
        
        # 预处理：将 pandas NaT/NaN 转换为 Python None，并清理字符串
        df["占用订单号"] = df["占用订单号"].apply(lambda v: None if str(v).strip() in ("", "nan", "None", "NaT") else str(v).strip())
        for dt_col in ["预计入库时间", "更新时间"]:
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
            
        fill_cols = [c for c in INVENTORY_COLS if c not in ["预计入库时间", "更新时间", "占用订单号"]]
        for col in fill_cols:
            df[col] = df[col].fillna("").astype(str).str.strip()

        with get_engine().begin() as conn:
            _ensure_finished_goods_contract_note_column(conn)
            # 确保 Location_Code 列存在
            result = conn.execute(text("SHOW COLUMNS FROM finished_goods_data LIKE 'Location_Code'"))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `Location_Code` VARCHAR(100) DEFAULT ''"))
            if not _has_column(conn, "finished_goods_data", "合同号"):
                conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `合同号` VARCHAR(100) DEFAULT ''"))

            if df.empty:
                enqueue_wechat_batch_summary_sync("finished_goods_save_v2_empty")
                return {"inserted": 0, "updated": 0}

            # UPSERT 语句: INSERT ... ON DUPLICATE KEY UPDATE
            # 注意: 流水号 是主键，冲突时会自动触发 UPDATE
            upsert_sql = text("""
                INSERT INTO finished_goods_data (
                    `流水号`, `批次号`, `机型`, `状态`, `预计入库时间`, `更新时间`,
                    `占用订单号`, `客户`, `代理商`, `合同备注`, `Location_Code`, `合同号`
                ) VALUES (
                    :流水号, :批次号, :机型, :状态, :预计入库时间, :更新时间,
                    :占用订单号, :客户, :代理商, :合同备注, :Location_Code, :合同号
                ) ON DUPLICATE KEY UPDATE
                    `批次号` = VALUES(`批次号`),
                    `机型` = VALUES(`机型`),
                    `状态` = VALUES(`状态`),
                    `预计入库时间` = VALUES(`预计入库时间`),
                    `更新时间` = VALUES(`更新时间`),
                    `占用订单号` = VALUES(`占用订单号`),
                    `客户` = VALUES(`客户`),
                    `代理商` = VALUES(`代理商`),
                    `合同备注` = VALUES(`合同备注`),
                    `Location_Code` = VALUES(`Location_Code`),
                    `合同号` = VALUES(`合同号`)
            """)

            # 转换为 Python 字典列表
            rows = df[INVENTORY_COLS].to_dict('records')
            
            # 手动清洗 dict 中的 NaT/Timestamp 对象，防止 PyMySQL 报错
            for r in rows:
                for k in ["预计入库时间", "更新时间"]:
                    val = r[k]
                    if pd.isna(val):
                        r[k] = None
                    elif hasattr(val, 'to_pydatetime'):
                        r[k] = val.to_pydatetime()

            # 使用 SQLAlchemy 批量绑定参数执行 (executemany)
            result = conn.execute(upsert_sql, rows)
            affected = result.rowcount if result.rowcount is not None else len(rows)

        enqueue_wechat_batch_summary_sync("finished_goods_save_v2")
        return {"inserted": affected, "updated": 0}

    except (OperationalError, Exception) as e:
        raise RuntimeError(f"保存失败: {e}") from e


def archive_shipped_data(df_shipped):
    try:
        current_month = datetime.now().strftime("%Y_%m")
        df_shipped = df_shipped.copy()
        df_shipped['archive_month'] = current_month
        for dt_col in ["预计入库时间", "更新时间"]:
            if dt_col in df_shipped.columns:
                df_shipped[dt_col] = pd.to_datetime(df_shipped[dt_col], errors="coerce")
        engine = get_engine()
        with engine.begin() as conn:
            if not _has_column(conn, "shipping_history", "合同备注"):
                conn.execute(text("ALTER TABLE shipping_history ADD COLUMN `合同备注` TEXT AFTER `代理商`"))
            if not _has_column(conn, "shipping_history", "合同号"):
                conn.execute(text("ALTER TABLE shipping_history ADD COLUMN `合同号` VARCHAR(100) DEFAULT ''"))
            target_cols = [
                row[0] for row in conn.execute(text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'shipping_history'"
                )).fetchall()
            ]
        df_shipped = df_shipped[[col for col in target_cols if col in df_shipped.columns]]
        df_shipped.fillna("").to_sql('shipping_history', engine, if_exists='append', index=False, method='multi', chunksize=500)
    except (OperationalError, Exception) as e:
        print(f"archive_shipped_data error: {e}")


def get_import_staging():
    try:
        with get_engine().begin() as conn:
            _ensure_plan_import_status_column(conn)
            _ensure_plan_import_trace_columns(conn)
            df = pd.read_sql("SELECT * FROM plan_import", conn)
        df = df.fillna("")
        if "预计入库时间" in df.columns:
            dt_series = pd.to_datetime(df["预计入库时间"], errors="coerce")
            df["预计入库时间"] = dt_series.dt.strftime("%Y-%m-%d").fillna("")
        return df
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"读取待入库数据失败: {e}") from e


def save_import_staging(df):
    try:
        df = _normalize_import_df(df)
        with get_engine().begin() as conn:
            _ensure_plan_import_status_column(conn)
            _ensure_plan_import_trace_columns(conn)
            conn.execute(text("DELETE FROM plan_import"))
            if not df.empty:
                df.to_sql('plan_import', conn, if_exists='append', index=False, method='multi')
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"保存待入库数据失败: {e}") from e


def append_import_staging(df):
    if df is None or df.empty:
        return 0
    try:
        df = _normalize_import_df(df)
        if df.empty:
            return 0
        df = df.drop_duplicates(subset=["流水号"], keep="last")
        with get_engine().begin() as conn:
            _ensure_plan_import_status_column(conn)
            _ensure_plan_import_trace_columns(conn)
            existing_df = pd.read_sql("SELECT 流水号 FROM plan_import", conn)
            existing_sns = set(existing_df["流水号"].astype(str).str.strip().tolist()) if not existing_df.empty else set()
            df_to_append = df[~df["流水号"].isin(existing_sns)].copy()
            if df_to_append.empty:
                return 0
            df_to_append.to_sql('plan_import', conn, if_exists='append', index=False, method='multi')
            return len(df_to_append)
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"追加待入库数据失败: {e}") from e


def append_import_staging_transactional(df):
    if df is None or df.empty:
        return {"ok": True, "inserted": 0, "error_code": ""}
    conn = None
    trans = None
    try:
        normalized_df = _normalize_import_df(df)
        if normalized_df.empty:
            return {"ok": True, "inserted": 0, "error_code": ""}
        conn = get_engine().connect()
        trans = conn.begin()
        _ensure_plan_import_status_column(conn)
        _ensure_plan_import_trace_columns(conn)
        existing_df = pd.read_sql("SELECT 流水号 FROM plan_import", conn)
        existing_sns = set(existing_df["流水号"].astype(str).str.strip().tolist()) if not existing_df.empty else set()
        df_to_append = normalized_df[~normalized_df["流水号"].isin(existing_sns)].copy()
        if df_to_append.empty:
            trans.commit()
            return {"ok": True, "inserted": 0, "error_code": ""}
        df_to_append.to_sql('plan_import', conn, if_exists='append', index=False, method='multi')
        trans.commit()
        return {"ok": True, "inserted": len(df_to_append), "error_code": ""}
    except Exception as e:
        if trans is not None:
            trans.rollback()
        logger.exception("append_import_staging_transactional failed")
        return {"ok": False, "inserted": 0, "error_code": "E_IMPORT_TXN_ROLLBACK", "message": str(e)}
    finally:
        if conn is not None:
            conn.close()

def get_inventory_summary():
    """按机型、状态分组汇总库存数据（SQL下推聚合）"""
    query = """
        SELECT `机型`, `状态`, COUNT(*) as count 
        FROM finished_goods_data 
        GROUP BY `机型`, `状态`
    """
    return fetch_data_with_cache(query, ttl=30)

def get_inventory_by_status(status_list: list, prefix_list: list = None):
    """获取指定状态或状态前缀的库存数据（避免全表扫描）"""
    if not status_list and not prefix_list:
        return pd.DataFrame(columns=INVENTORY_COLS)
    
    conditions = []
    params = {}
    
    if status_list:
        placeholders = ", ".join([f":s{i}" for i in range(len(status_list))])
        conditions.append(f"`状态` IN ({placeholders})")
        for i, status in enumerate(status_list):
            params[f"s{i}"] = status
            
    if prefix_list:
        for i, prefix in enumerate(prefix_list):
            conditions.append(f"`状态` LIKE :p{i}")
            params[f"p{i}"] = f"{prefix}%"
            
    where_clause = " OR ".join(conditions)
    query = f"SELECT * FROM finished_goods_data WHERE {where_clause}"
    
    df = fetch_data_with_cache(query, params, ttl=30)
    if df.empty:
        return pd.DataFrame(columns=INVENTORY_COLS)
    return df



def clear_import_staging():
    try:
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM plan_import"))
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"清空待入库数据失败: {e}") from e


def delete_import_staging_by_serials(serial_nos):
    cleaned = [str(sn).strip() for sn in (serial_nos or []) if str(sn).strip()]
    if not cleaned:
        return {"deleted": 0, "orphaned_batch_codes": []}
    try:
        with get_engine().begin() as conn:
            placeholders = ", ".join([f":sn{i}" for i in range(len(cleaned))])
            params = {f"sn{i}": sn for i, sn in enumerate(cleaned)}

            # Collect affected batch_codes before deletion
            affected_rows = conn.execute(
                text(f"SELECT DISTINCT `批次号` FROM plan_import WHERE `流水号` IN ({placeholders})"),
                params,
            ).fetchall()
            affected_codes = [
                str(r[0]).strip() for r in affected_rows
                if r[0] and str(r[0]).strip()
            ]

            # Delete the records
            result = conn.execute(
                text(f"DELETE FROM plan_import WHERE `流水号` IN ({placeholders})"),
                params,
            )
            deleted = int(result.rowcount or 0)

            # Check which batch_codes no longer have any records
            orphaned = []
            for bc in affected_codes:
                remaining = conn.execute(
                    text("SELECT COUNT(*) FROM plan_import WHERE `批次号` = :bc"),
                    {"bc": bc},
                ).scalar()
                if not remaining:
                    orphaned.append(bc)

            return {"deleted": deleted, "orphaned_batch_codes": orphaned}
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"删除待入库数据失败: {e}") from e


def get_warehouse_layout(layout_id="default"):
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT layout_json, update_time FROM warehouse_layout WHERE layout_id=:layout_id"),
                {"layout_id": layout_id},
            ).fetchone()
        if row is None:
            return {"layout_id": layout_id, "layout_json": {"slots": []}, "update_time": ""}
        raw_json = row[0] if len(row) > 0 else "{}"
        parsed = json.loads(raw_json) if raw_json else {"slots": []}
        return {"layout_id": layout_id, "layout_json": enrich_warehouse_layout(parsed), "update_time": str(row[1] or "")}
    except Exception as e:
        raise RuntimeError(f"读取库位布局失败: {e}") from e


def save_warehouse_layout(layout_id, layout_json):
    try:
        clean_layout = sanitize_warehouse_layout(layout_json)
        payload = json.dumps(clean_layout, ensure_ascii=False)
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO warehouse_layout(layout_id, layout_json, update_time) "
                    "VALUES(:layout_id, :layout_json, NOW()) "
                    "ON DUPLICATE KEY UPDATE layout_json=VALUES(layout_json), update_time=VALUES(update_time)"
                ),
                {"layout_id": layout_id, "layout_json": payload},
            )
    except Exception:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO warehouse_layout(layout_id, layout_json, update_time) "
                    "VALUES(:layout_id, :layout_json, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(layout_id) DO UPDATE SET layout_json=excluded.layout_json, update_time=CURRENT_TIMESTAMP"
                ),
                {"layout_id": layout_id, "layout_json": json.dumps(sanitize_warehouse_layout(layout_json), ensure_ascii=False)},
            )
    return get_warehouse_layout(layout_id)


def reset_warehouse_layout(layout_id="default"):
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM warehouse_layout WHERE layout_id=:layout_id"), {"layout_id": layout_id})
    return {"layout_id": layout_id, "layout_json": {"slots": []}, "update_time": ""}


def inbound_to_slot(serial_no, slot_code, is_transfer=False, operator=""):
    if not serial_no or not slot_code:
        return {"ok": False, "code": "E_INVALID_PARAM", "message": "流水号与库位号不能为空"}
    slot_code = canonical_slot_code(slot_code)
    slot_capacity = get_slot_capacity(slot_code)
    scrap_slot = is_scrap_slot(slot_code)
    unlimited_slot = is_unlimited_slot(slot_code)
        
    # 检查库位是否被锁定或异常
    layout_resp = get_warehouse_layout("default")
    slots = layout_resp.get("layout_json", {}).get("slots", [])
    target_slot = next((s for s in slots if s.get("code") == slot_code), None)
    if target_slot and target_slot.get("status") in ["锁定", "异常"]:
        return {"ok": False, "code": "E_SLOT_LOCKED", "message": f"库位 {slot_code} 处于{target_slot.get('status')}状态，无法入库"}
        
    conn = None
    trans = None
    try:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_engine().connect()
        trans = conn.begin()
        stats_df = pd.read_sql(
            "SELECT `流水号`, `Location_Code`, `状态`, `更新时间` FROM finished_goods_data",
            conn,
        )
        slot_df = stats_df[stats_df["Location_Code"].astype(str).str.strip() == str(slot_code).strip()]
        status_series = slot_df["状态"].astype(str).str.strip()
        if scrap_slot:
            active_slot_df = slot_df[status_series == "报废"]
        else:
            active_slot_df = slot_df[status_series.str.contains("库存中", na=False)]
        if not unlimited_slot and len(active_slot_df) >= slot_capacity:
            trans.rollback()
            return {"ok": False, "code": "E_SLOT_FULL", "message": f"库位 {slot_code} 已满载"}
        row = conn.execute(
            text("SELECT `流水号`, `状态` FROM finished_goods_data WHERE `流水号`=:sn FOR UPDATE"),
            {"sn": serial_no},
        ).fetchone()
        if row is None:
            trans.rollback()
            return {"ok": False, "code": "E_NOT_FOUND", "message": "机台不存在"}
        current_status = str(row[1] or "").strip()
        if current_status == "报废" and not scrap_slot:
            trans.rollback()
            return {"ok": False, "code": "E_SCRAPPED", "message": "报废机台不能调拨到普通库位"}
        if not is_transfer and current_status.startswith("库存中"):
            trans.rollback()
            return {"ok": False, "code": "E_ALREADY_INBOUND", "message": "机台已入库"}
        status_after = "报废" if scrap_slot else f"库存中（{slot_code}）"
        conn.execute(
            text(
                "UPDATE finished_goods_data "
                "SET `状态`=:status, `Location_Code`=:slot_code, `更新时间`=:updated_at "
                "WHERE `流水号`=:sn"
            ),
            {"status": status_after, "slot_code": slot_code, "updated_at": now_text, "sn": serial_no},
        )
        if not is_transfer:
            record_inbound_history(
                conn,
                [serial_no],
                source="机台入库",
                operator=operator,
                slot_code=slot_code,
                inbound_time=now_text,
                status_before=current_status,
                status_after=status_after,
            )
        trans.commit()
        completed_batches = []
        if not is_transfer:
            completed_batches = notify_inbound_completion([serial_no], operator=operator)
        enqueue_wechat_batch_summary_sync("finished_goods_inbound")
        get_data.cache_clear()
        get_data_v2.cache_clear()  # 清除 v2 缓存，确保下次读取到最新库存状态
        try:
            from api.websockets.manager import manager
            manager.broadcast_from_sync({"type": "INVENTORY_UPDATE", "serial_no": serial_no, "slot_code": slot_code})
        except ImportError:
            pass
            
        action_msg = "调拨成功" if is_transfer else "入库成功"
        return {
            "ok": True,
            "code": "OK",
            "message": action_msg,
            "inbound_time": now_text,
            "slot_code": slot_code,
            "auto_completed_batches": completed_batches,
        }
    except Exception as e:
        if trans is not None:
            trans.rollback()
        return {"ok": False, "code": "E_TXN_ROLLBACK", "message": str(e)}
    finally:
        if conn is not None:
            conn.close()


def inbound_to_slot_v2(serial_no, slot_code, is_transfer=False, operator=""):
    """
    优化版入库函数：使用 SQL COUNT 替代全表扫描
    解决 P1 性能问题：原函数读取全表到 Python 内存过滤
    """
    if not serial_no or not slot_code:
        return {"ok": False, "code": "E_INVALID_PARAM", "message": "流水号与库位号不能为空"}
    slot_code = canonical_slot_code(slot_code)
    slot_capacity = get_slot_capacity(slot_code)
    scrap_slot = is_scrap_slot(slot_code)
    unlimited_slot = is_unlimited_slot(slot_code)

    # 检查库位是否被锁定或异常
    layout_resp = get_warehouse_layout("default")
    slots = layout_resp.get("layout_json", {}).get("slots", [])
    target_slot = next((s for s in slots if s.get("code") == slot_code), None)
    if target_slot and target_slot.get("status") in ["锁定", "异常"]:
        return {"ok": False, "code": "E_SLOT_LOCKED", "message": f"库位 {slot_code} 处于{target_slot.get('status')}状态，无法入库"}

    conn = None
    trans = None
    try:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_engine().connect()
        trans = conn.begin()

        if not unlimited_slot:
            # 优化：使用 SQL COUNT 替代全表读取
            # 原代码：stats_df = pd.read_sql("SELECT ... FROM finished_goods_data", conn)
            # 新代码：直接在数据库层统计
            slot_status_condition = "`状态` = '报废'" if scrap_slot else "`状态` LIKE '库存中%'"
            slot_count = conn.execute(
                text(f"""
                    SELECT COUNT(*) as cnt
                    FROM finished_goods_data
                    WHERE `Location_Code` = :slot_code
                    AND {slot_status_condition}
                """),
                {"slot_code": slot_code}
            ).scalar()

            if slot_count >= slot_capacity:
                trans.rollback()
                return {"ok": False, "code": "E_SLOT_FULL", "message": f"库位 {slot_code} 已满载"}

        # 检查机台状态（保持不变）
        row = conn.execute(
            text("SELECT `流水号`, `状态` FROM finished_goods_data WHERE `流水号`=:sn FOR UPDATE"),
            {"sn": serial_no},
        ).fetchone()
        if row is None:
            trans.rollback()
            return {"ok": False, "code": "E_NOT_FOUND", "message": "机台不存在"}
        current_status = str(row[1] or "").strip()
        if current_status == "报废" and not scrap_slot:
            trans.rollback()
            return {"ok": False, "code": "E_SCRAPPED", "message": "报废机台不能调拨到普通库位"}
        if not is_transfer and current_status.startswith("库存中"):
            trans.rollback()
            return {"ok": False, "code": "E_ALREADY_INBOUND", "message": "机台已入库"}

        # 更新入库（保持不变）
        status_after = "报废" if scrap_slot else f"库存中（{slot_code}）"
        conn.execute(
            text(
                "UPDATE finished_goods_data "
                "SET `状态`=:status, `Location_Code`=:slot_code, `更新时间`=:updated_at "
                "WHERE `流水号`=:sn"
            ),
            {"status": status_after, "slot_code": slot_code, "updated_at": now_text, "sn": serial_no},
        )
        if not is_transfer:
            record_inbound_history(
                conn,
                [serial_no],
                source="机台入库",
                operator=operator,
                slot_code=slot_code,
                inbound_time=now_text,
                status_before=current_status,
                status_after=status_after,
            )
        trans.commit()
        completed_batches = []
        if not is_transfer:
            completed_batches = notify_inbound_completion([serial_no], operator=operator)
        enqueue_wechat_batch_summary_sync("finished_goods_inbound_v2")

        # 清除所有缓存版本
        get_data.cache_clear()
        get_data_v2.cache_clear()

        # WebSocket 广播（保持不变）
        try:
            import asyncio
            from api.websockets.manager import manager
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.broadcast({"type": "INVENTORY_UPDATE", "serial_no": serial_no, "slot_code": slot_code}))
                else:
                    loop.run_until_complete(manager.broadcast({"type": "INVENTORY_UPDATE", "serial_no": serial_no, "slot_code": slot_code}))
            except Exception:
                pass
        except ImportError:
            pass

        action_msg = "调拨成功" if is_transfer else "入库成功"
        return {
            "ok": True,
            "code": "OK",
            "message": action_msg,
            "inbound_time": now_text,
            "slot_code": slot_code,
            "auto_completed_batches": completed_batches,
        }
    except Exception as e:
        if trans is not None:
            trans.rollback()
        return {"ok": False, "code": "E_TXN_ROLLBACK", "message": str(e)}
    finally:
        if conn is not None:
            conn.close()
