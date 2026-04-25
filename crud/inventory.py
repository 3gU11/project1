import json
import logging
from datetime import datetime
from functools import lru_cache

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import get_engine
from utils.cache import fetch_data_with_cache
from utils.local_cache import ttl_cache


logger = logging.getLogger(__name__)
INVENTORY_COLS = ["批次号", "机型", "流水号", "状态", "预计入库时间", "更新时间", "占用订单号", "客户", "代理商", "订单备注", "机台备注/配置", "Location_Code"]
IMPORT_COLS = ["流水号", "批次号", "机型", "状态", "预计入库时间", "机台备注/配置"]
WAREHOUSE_MAX_CAPACITY = 5


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
        df = df.fillna("")
        for col in INVENTORY_COLS:
            if col not in df.columns:
                df[col] = ""
        if '备注' in df.columns and '订单备注' not in df.columns:
            df.rename(columns={'备注': '订单备注'}, inplace=True)
            
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
        df = df.fillna("")
        for col in INVENTORY_COLS:
            if col not in df.columns:
                df[col] = ""
        if '备注' in df.columns and '订单备注' not in df.columns:
            df.rename(columns={'备注': '订单备注'}, inplace=True)

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


def save_data(df):
    get_data.cache_clear()
    get_data_v2.cache_clear()  # 同时清除 v2 版本缓存
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
            result = conn.execute(text("SHOW COLUMNS FROM finished_goods_data LIKE 'Location_Code'"))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `Location_Code` VARCHAR(100) DEFAULT ''"))
            conn.execute(text("DELETE FROM finished_goods_data"))
            if not df.empty:
                df[INVENTORY_COLS].to_sql('finished_goods_data', conn, if_exists='append', index=False, method='multi', chunksize=500)
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"保存失败: {e}") from e


def save_data_v2(df):
    """
    优化版 save_data：使用 UPSERT (INSERT ... ON DUPLICATE KEY UPDATE)
    避免 DELETE + INSERT 全表重写，大幅提升性能
    """
    from sqlalchemy import bindparam

    get_data.cache_clear()
    get_data_v2.cache_clear()

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
            # 确保 Location_Code 列存在
            result = conn.execute(text("SHOW COLUMNS FROM finished_goods_data LIKE 'Location_Code'"))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE finished_goods_data ADD COLUMN `Location_Code` VARCHAR(100) DEFAULT ''"))

            if df.empty:
                return {"inserted": 0, "updated": 0}

            # UPSERT 语句: INSERT ... ON DUPLICATE KEY UPDATE
            # 注意: 流水号 是主键，冲突时会自动触发 UPDATE
            upsert_sql = text("""
                INSERT INTO finished_goods_data (
                    `流水号`, `批次号`, `机型`, `状态`, `预计入库时间`, `更新时间`,
                    `占用订单号`, `客户`, `代理商`, `订单备注`, `机台备注/配置`, `Location_Code`
                ) VALUES (
                    :流水号, :批次号, :机型, :状态, :预计入库时间, :更新时间,
                    :占用订单号, :客户, :代理商, :订单备注, :机台备注/配置, :Location_Code
                ) ON DUPLICATE KEY UPDATE
                    `批次号` = VALUES(`批次号`),
                    `机型` = VALUES(`机型`),
                    `状态` = VALUES(`状态`),
                    `预计入库时间` = VALUES(`预计入库时间`),
                    `更新时间` = VALUES(`更新时间`),
                    `占用订单号` = VALUES(`占用订单号`),
                    `客户` = VALUES(`客户`),
                    `代理商` = VALUES(`代理商`),
                    `订单备注` = VALUES(`订单备注`),
                    `机台备注/配置` = VALUES(`机台备注/配置`),
                    `Location_Code` = VALUES(`Location_Code`)
            """)

            # 分批处理，避免单条 SQL 过长
            CHUNK_SIZE = 500
            inserted = 0
            updated = 0

            for start in range(0, len(df), CHUNK_SIZE):
                chunk = df.iloc[start:start + CHUNK_SIZE]
                rows = chunk[INVENTORY_COLS].to_dict('records')

                for row in rows:
                    result = conn.execute(upsert_sql, row)
                    # 根据 MySQL 返回的 rowcount 判断是 INSERT 还是 UPDATE
                    # rowcount=1 表示 INSERT, rowcount=2 表示 UPDATE (MySQL 特性)
                    if result.rowcount == 1:
                        inserted += 1
                    elif result.rowcount == 2:
                        updated += 1
                    else:
                        # 对于某些驱动，可能无法区分，统一计为更新
                        inserted += 1

        return {"inserted": inserted, "updated": updated}

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
        df_shipped.fillna("").to_sql('shipping_history', get_engine(), if_exists='append', index=False, method='multi', chunksize=500)
    except (OperationalError, Exception) as e:
        print(f"archive_shipped_data error: {e}")


def get_import_staging():
    try:
        with get_engine().begin() as conn:
            _ensure_plan_import_status_column(conn)
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
        return 0
    try:
        with get_engine().begin() as conn:
            placeholders = ", ".join([f":sn{i}" for i in range(len(cleaned))])
            params = {f"sn{i}": sn for i, sn in enumerate(cleaned)}
            result = conn.execute(
                text(f"DELETE FROM plan_import WHERE `流水号` IN ({placeholders})"),
                params,
            )
            return int(result.rowcount or 0)
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
        return {"layout_id": layout_id, "layout_json": parsed, "update_time": str(row[1] or "")}
    except Exception as e:
        raise RuntimeError(f"读取库位布局失败: {e}") from e


def save_warehouse_layout(layout_id, layout_json):
    try:
        payload = json.dumps(layout_json, ensure_ascii=False)
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
                {"layout_id": layout_id, "layout_json": json.dumps(layout_json, ensure_ascii=False)},
            )
    return get_warehouse_layout(layout_id)


def reset_warehouse_layout(layout_id="default"):
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM warehouse_layout WHERE layout_id=:layout_id"), {"layout_id": layout_id})
    return {"layout_id": layout_id, "layout_json": {"slots": []}, "update_time": ""}


def inbound_to_slot(serial_no, slot_code, is_transfer=False):
    if not serial_no or not slot_code:
        return {"ok": False, "code": "E_INVALID_PARAM", "message": "流水号与库位号不能为空"}
        
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
        active_slot_df = slot_df[slot_df["状态"].astype(str).str.contains("库存中", na=False)]
        if len(active_slot_df) >= WAREHOUSE_MAX_CAPACITY:
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
        if not is_transfer and current_status.startswith("库存中"):
            trans.rollback()
            return {"ok": False, "code": "E_ALREADY_INBOUND", "message": "机台已入库"}
        conn.execute(
            text(
                "UPDATE finished_goods_data "
                "SET `状态`=:status, `Location_Code`=:slot_code, `更新时间`=:updated_at "
                "WHERE `流水号`=:sn"
            ),
            {"status": f"库存中（{slot_code}）", "slot_code": slot_code, "updated_at": now_text, "sn": serial_no},
        )
        trans.commit()
        get_data.cache_clear()  # 清除缓存，确保下次读取到最新库存状态
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
        return {"ok": True, "code": "OK", "message": action_msg, "inbound_time": now_text, "slot_code": slot_code}
    except Exception as e:
        if trans is not None:
            trans.rollback()
        return {"ok": False, "code": "E_TXN_ROLLBACK", "message": str(e)}
    finally:
        if conn is not None:
            conn.close()


def inbound_to_slot_v2(serial_no, slot_code, is_transfer=False):
    """
    优化版入库函数：使用 SQL COUNT 替代全表扫描
    解决 P1 性能问题：原函数读取全表到 Python 内存过滤
    """
    if not serial_no or not slot_code:
        return {"ok": False, "code": "E_INVALID_PARAM", "message": "流水号与库位号不能为空"}

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

        # 优化：使用 SQL COUNT 替代全表读取
        # 原代码：stats_df = pd.read_sql("SELECT ... FROM finished_goods_data", conn)
        # 新代码：直接在数据库层统计
        slot_count = conn.execute(
            text("""
                SELECT COUNT(*) as cnt
                FROM finished_goods_data
                WHERE `Location_Code` = :slot_code
                AND `状态` LIKE '库存中%'
            """),
            {"slot_code": slot_code}
        ).scalar()

        if slot_count >= WAREHOUSE_MAX_CAPACITY:
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
        if not is_transfer and current_status.startswith("库存中"):
            trans.rollback()
            return {"ok": False, "code": "E_ALREADY_INBOUND", "message": "机台已入库"}

        # 更新入库（保持不变）
        conn.execute(
            text(
                "UPDATE finished_goods_data "
                "SET `状态`=:status, `Location_Code`=:slot_code, `更新时间`=:updated_at "
                "WHERE `流水号`=:sn"
            ),
            {"status": f"库存中（{slot_code}）", "slot_code": slot_code, "updated_at": now_text, "sn": serial_no},
        )
        trans.commit()

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
        return {"ok": True, "code": "OK", "message": action_msg, "inbound_time": now_text, "slot_code": slot_code}
    except Exception as e:
        if trans is not None:
            trans.rollback()
        return {"ok": False, "code": "E_TXN_ROLLBACK", "message": str(e)}
    finally:
        if conn is not None:
            conn.close()
