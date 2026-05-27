from typing import List, Dict, Any
from urllib.parse import unquote
import base64
import re
import asyncio

import os
import uuid
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query, Request, BackgroundTasks
import httpx
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import json
from sqlalchemy import bindparam, text

from config import BASE_DIR, GO_SANDBOX_URL, GO_INTERNAL_TOKEN
from core.file_manager import delete_contract_file, save_contract_file
from crud.audit_logs import append_audit_log
from crud.contracts import get_contract_files
from crud.inventory import get_data, save_data
from crud.logs import append_log
from crud.model_dictionary import is_model_enabled
from crud.planning import get_factory_plan, get_factory_plan_v2, save_factory_plan
from crud.orders import allocate_inventory, get_orders, revert_to_inbound, save_orders
from api.routes.auth import get_current_operator_name, get_current_user_context, get_current_user_token
from utils.parsers import parse_alloc_dict
from database import get_engine

router = APIRouter(dependencies=[Depends(get_current_user_token)])


def _parse_order_need_total(row: pd.Series) -> int:
    raw = str(row.get("需求机型", "") or "")
    total = 0
    for token_raw in re.split(r"[;；/,，]", raw):
        token = token_raw.strip()
        if not token:
            continue
        # 兼容 x3 / ×3 / :3
        m = re.search(r"(?:[x×:：]\s*)(\d+)\s*$", token, flags=re.IGNORECASE)
        if m:
            total += int(m.group(1))
    if total > 0:
        return total
    try:
        fallback = int(row.get("需求数量", 0) or 0)
    except Exception:
        fallback = 0
    return max(0, fallback)


def _parse_order_demand_counts(row: pd.Series) -> dict[str, int]:
    raw = str(row.get("需求机型", "") or "")
    counts: dict[str, int] = {}
    for token_raw in raw.split(";"):
        token = token_raw.strip()
        if not token:
            continue
        m = re.search(r"(?:[x×:：]\s*)(\d+)\s*$", token, flags=re.IGNORECASE)
        qty = int(m.group(1)) if m else 0
        model = re.sub(r"(?:[x×:：]\s*)\d+\s*$", "", token, flags=re.IGNORECASE).strip()
        model = model.replace("(加高)", "").strip()
        if model and qty > 0:
            counts[model] = counts.get(model, 0) + qty
    if counts:
        return counts
    fallback_model = raw.strip()
    fallback_qty = _parse_order_need_total(row)
    if fallback_model and fallback_qty > 0:
        return {fallback_model: fallback_qty}
    return {}


def _extract_models_from_demand_text(raw_text: str) -> list[str]:
    models: list[str] = []
    raw = str(raw_text or "")
    for token_raw in raw.split(";"):
        token = token_raw.strip()
        if not token:
            continue
        model_part = re.sub(r"(?:[x×:：]\s*)\d+\s*$", "", token, flags=re.IGNORECASE).strip()
        model_name = model_part.replace("(加高)", "").strip()
        if model_name:
            models.append(model_name)
    return models


def _assert_models_in_dictionary(models: list[str]) -> None:
    invalid = [m for m in models if m and not is_model_enabled(m)]
    if invalid:
        unique_invalid = []
        seen = set()
        for item in invalid:
            if item not in seen:
                seen.add(item)
                unique_invalid.append(item)
        raise HTTPException(status_code=422, detail=f"机型不在字典中或未启用: {'，'.join(unique_invalid)}")


def _reconcile_completed_orders(df_orders: pd.DataFrame) -> pd.DataFrame:
    if df_orders.empty:
        return df_orders
    inv_df = get_data()
    if inv_df.empty:
        return df_orders

    shipped_by_order: Dict[str, int] = {}
    shipped_rows = inv_df[inv_df["状态"].astype(str) == "已出库"]
    for _, r in shipped_rows.iterrows():
        oid = str(r.get("占用订单号", "") or "").strip()
        if not oid:
            continue
        shipped_by_order[oid] = shipped_by_order.get(oid, 0) + 1

    changed = False
    for idx, row in df_orders.iterrows():
        oid = str(row.get("订单号", "") or "").strip()
        if not oid:
            continue
        status = str(row.get("status", "active") or "active")
        if status in ("deleted", "done"):
            continue
        need = _parse_order_need_total(row)
        shipped = shipped_by_order.get(oid, 0)
        if need > 0 and shipped >= need:
            df_orders.at[idx, "status"] = "done"
            changed = True

    if changed:
        save_orders(df_orders)
    return df_orders


class ContractItem(BaseModel):
    机型: str
    排产数量: int = Field(gt=0)
    备注: str = ""


class ContractEditPayload(BaseModel):
    客户名: str
    代理商: str
    要求交期: str
    items: List[ContractItem]


class StatusPayload(BaseModel):
    status: str


class PlanRowPayload(BaseModel):
    row_index: int
    allocation: Dict[str, int] = Field(default_factory=dict)


class PlanSavePayload(BaseModel):
    rows: List[PlanRowPayload]
    mark_to_planned: bool = True


class SalesOrderCreatePayload(BaseModel):
    客户名: str
    代理商: str = ""
    需求机型: str
    需求数量: int = Field(gt=0)
    备注: str = ""
    包装选项: str = ""
    发货时间: str = ""
    contract_ids: List[str] = Field(default_factory=list)


class SalesOrderUpdatePayload(BaseModel):
    客户名: str | None = None
    代理商: str | None = None
    需求机型: str | None = None
    需求数量: int | None = None
    备注: str | None = None
    包装选项: str | None = None
    发货时间: str | None = None
    status: str | None = None


class OrderAllocatePayload(BaseModel):
    selected_serial_nos: List[str] = Field(default_factory=list)


class OrderReleasePayload(BaseModel):
    selected_serial_nos: List[str] = Field(default_factory=list)
    all: bool = False


class BatchContractRowPayload(BaseModel):
    合同号: str
    客户名: str
    代理商: str = ""
    机型: str
    排产数量: int = Field(gt=0)
    要求交期: str
    备注: str = ""


class BatchContractCreatePayload(BaseModel):
    rows: List[BatchContractRowPayload]
    is_rush: bool = False
    save_mode: str = "sandbox"  # sandbox | spot
    dealer_order_no: str = ""  # 来源经销商订单号，创建成功后回写contract_no


class LinkOrderPayload(BaseModel):
    order_id: str


def _insert_production_queue(rows: list[dict[str, Any]]) -> int:
    """新合同录入后同步写入 production_queue，走排产队列调度。"""
    if not rows:
        return 0
    insert_values: list[dict[str, Any]] = []
    for row in rows:
        qty = int(row.get("排产数量") or 0)
        if qty <= 0:
            continue
        insert_values.append({
            "model_type": str(row.get("机型") or "").strip(),
            "contract_no": str(row.get("合同号") or "").strip(),
            "customer": str(row.get("客户名") or "").strip(),
            "dealer": str(row.get("代理商") or "").strip(),
            "due_date": str(row.get("要求交期") or "").strip(),
            "quantity_remaining": qty,
        })
    if not insert_values:
        return 0
    with get_engine().begin() as conn:
        for v in insert_values:
            result = conn.execute(
                text(
                    "UPDATE production_queue SET quantity_remaining = quantity_remaining + :qty "
                    "WHERE contract_no = :cid AND model_type = :model AND status = 'Waiting'"
                ),
                {"qty": v["quantity_remaining"], "cid": v["contract_no"], "model": v["model_type"]},
            )
            if result.rowcount == 0:
                conn.execute(
                    text(
                        "INSERT INTO production_queue (model_type, contract_no, customer, dealer, due_date, quantity_remaining, status) "
                        "VALUES (:model_type, :contract_no, :customer, :dealer, :due_date, :quantity_remaining, 'Waiting')"
                    ),
                    v,
                )
    return len(insert_values)


def _trigger_sandbox_recompute_sync(user_ctx: dict):
    headers = {
        "Content-Type": "application/json",
        "X-Username": str(user_ctx.get("username") or ""),
        "X-Role": str(user_ctx.get("role") or ""),
    }
    if GO_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = GO_INTERNAL_TOKEN
    
    try:
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            client.post(f"{GO_SANDBOX_URL}/api/forecast/recompute", headers=headers)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Auto-recompute failed: {e}")


def _auto_insert_rush_orders(rows: list[dict[str, Any]], user_ctx: dict, current_operator: str = "") -> int:
    if not rows:
        return 0

    headers = {
        "Content-Type": "application/json",
        "X-Username": str(user_ctx.get("username") or current_operator or ""),
        "X-Role": str(user_ctx.get("role") or ""),
        "X-User-ID": str(user_ctx.get("username") or current_operator or ""),
    }
    if GO_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = GO_INTERNAL_TOKEN

    inserted = 0
    import logging
    logger = logging.getLogger(__name__)
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        for row in rows:
            qty = int(row.get("qty") or 0)
            # 从 指定批次/来源 字典中取第一个批次号作为优先插入批次
            source_alloc = row.get("source_alloc") or {}
            preferred_batch_no = ""
            if isinstance(source_alloc, dict) and source_alloc:
                preferred_batch_no = str(next(iter(source_alloc), "")).strip()
            for _ in range(max(0, qty)):
                payload = {
                    "mode": "auto",
                    "rush_order": {
                        "contract_no": str(row.get("contract_no") or "").strip(),
                        "customer": str(row.get("customer") or "").strip(),
                        "model_type": str(row.get("model_type") or "").strip(),
                        "dealer_name": str(row.get("dealer_name") or "").strip(),
                        "due_date": str(row.get("due_date") or "").strip(),
                        "remark": str(row.get("remark") or "").strip(),
                        "preferred_batch_no": preferred_batch_no,
                    },
                    "reason": "急单录入后自动进入沙盘",
                }
                try:
                    resp = client.post(f"{GO_SANDBOX_URL}/api/units/rush-insert", headers=headers, json=payload)
                    if resp.status_code >= 400:
                        logger.warning("Rush auto insert failed for %s: %s", payload["rush_order"]["contract_no"], resp.text)
                        continue
                    with get_engine().begin() as conn:
                        conn.execute(text("""
                            UPDATE rush_order_queue
                            SET `status` = 'inserted', `updated_by` = :updated_by
                            WHERE `contract_no` = :contract_no
                              AND `model_type` = :model_type
                              AND COALESCE(`remark`, '') = :remark
                              AND `status` = 'pending'
                            ORDER BY id ASC
                            LIMIT 1
                        """), {
                            "updated_by": str(user_ctx.get("username") or current_operator or ""),
                            "contract_no": payload["rush_order"]["contract_no"],
                            "model_type": payload["rush_order"]["model_type"],
                            "remark": payload["rush_order"]["remark"],
                        })
                    inserted += 1
                except Exception as e:
                    logger.warning("Rush auto insert exception for %s: %s", payload["rush_order"]["contract_no"], e)
                    continue
    return inserted


def _insert_rush_order_queue(rows: list[dict[str, Any]], created_by: str = "") -> int:
    if not rows:
        return 0
    insert_rows: list[dict[str, Any]] = []
    for row in rows:
        qty = int(row.get("qty") or 0)
        if qty <= 0:
            continue
        contract_no = str(row.get("contract_no") or "").strip()
        model_type = str(row.get("model_type") or "").strip()
        if not contract_no or not model_type:
            continue
        due_date = str(row.get("due_date") or "").strip() or None
        for _ in range(qty):
            insert_rows.append({
                "contract_no": contract_no,
                "customer": str(row.get("customer") or "").strip(),
                "dealer_name": str(row.get("dealer_name") or "").strip(),
                "model_type": model_type,
                "due_date": due_date,
                "remark": str(row.get("remark") or "").strip(),
                "source": "contract",
                "status": "pending",
                "created_by": str(created_by or "").strip(),
                "updated_by": str(created_by or "").strip(),
            })
    if not insert_rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO rush_order_queue
                    (contract_no, customer, dealer_name, model_type, due_date, remark, source, status, created_by, updated_by)
                VALUES
                    (:contract_no, :customer, :dealer_name, :model_type, :due_date, :remark, :source, :status, :created_by, :updated_by)
            """),
            insert_rows,
        )
    return len(insert_rows)


def _clean_contract_ids(values: List[str] | None) -> list[str]:
    if isinstance(values, str):
        values = [v for v in re.split(r"[,\s;，；]+", values) if v]
    result: list[str] = []
    seen = set()
    for item in values or []:
        cid = str(item or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result


def _user_id_from_context(current_user) -> str:
    return current_user.get("username") if isinstance(current_user, dict) else ""


def _occupy_inventory_for_order(contract_ids: list[str], order_id: str) -> int:
    contract_ids = _clean_contract_ids(contract_ids)
    order_id = str(order_id or "").strip()
    if not contract_ids or not order_id:
        return 0
    with get_engine().begin() as conn:
        if not (
            _table_has_column(conn, "finished_goods_data", "合同号")
            and _table_has_column(conn, "finished_goods_data", "占用订单号")
            and _table_has_column(conn, "finished_goods_data", "状态")
        ):
            return 0
        ret = conn.execute(
            text(
                "UPDATE finished_goods_data "
                "SET `占用订单号` = :order_id "
                "WHERE TRIM(COALESCE(`合同号`, '')) COLLATE utf8mb4_general_ci IN :contract_ids "
                "AND TRIM(COALESCE(`状态`, '')) <> '已出库' "
                "AND (COALESCE(TRIM(`占用订单号`), '') = '' OR TRIM(`占用订单号`) = :order_id)"
            ).bindparams(bindparam("contract_ids", expanding=True)),
            {"contract_ids": contract_ids, "order_id": order_id},
        )
    return int(ret.rowcount or 0)


def _table_has_column(conn, table_name: str, column_name: str) -> bool:
    try:
        return conn.execute(
            text(f"SHOW COLUMNS FROM `{table_name}` LIKE :column_name"),
            {"column_name": column_name},
        ).fetchone() is not None
    except Exception:
        return False


def _ensure_plan_import_order_column(conn) -> None:
    if not _table_has_column(conn, "plan_import", "订单号"):
        conn.execute(text("ALTER TABLE plan_import ADD COLUMN `订单号` VARCHAR(100) DEFAULT '' AFTER `合同号`"))


def _sync_order_to_units_and_import(contract_ids: list[str], order_id: str) -> dict[str, int]:
    contract_ids = _clean_contract_ids(contract_ids)
    order_id = str(order_id or "").strip()
    if not contract_ids or not order_id:
        return {"units": 0, "plan_import": 0}

    with get_engine().begin() as conn:
        conflicts = conn.execute(
            text(
                "SELECT DISTINCT contract_no, sales_id FROM units "
                "WHERE TRIM(COALESCE(contract_no, '')) COLLATE utf8mb4_general_ci IN :contract_ids "
                "AND COALESCE(TRIM(sales_id), '') <> '' "
                "AND TRIM(sales_id) <> :order_id"
            ).bindparams(bindparam("contract_ids", expanding=True)),
            {"contract_ids": contract_ids, "order_id": order_id},
        ).fetchall()
        if conflicts:
            conflict_contract = str(conflicts[0][0] or "").strip()
            conflict_order = str(conflicts[0][1] or "").strip()
            raise HTTPException(status_code=422, detail=f"合同 {conflict_contract} 已绑定其他订单 {conflict_order}")

        unit_ret = conn.execute(
            text(
                "UPDATE units SET sales_id = :order_id, updated_at = NOW() "
                "WHERE TRIM(COALESCE(contract_no, '')) COLLATE utf8mb4_general_ci IN :contract_ids "
                "AND (sales_id IS NULL OR TRIM(sales_id) = '' OR TRIM(sales_id) = :order_id)"
            ).bindparams(bindparam("contract_ids", expanding=True)),
            {"contract_ids": contract_ids, "order_id": order_id},
        )

        finished_goods_rows = 0
        if _table_has_column(conn, "finished_goods_data", "流水号") and _table_has_column(conn, "finished_goods_data", "占用订单号"):
            unit_serial_rows = conn.execute(
                text(
                    "SELECT serial_no, forecast_serial_no, unit_id FROM units "
                    "WHERE TRIM(COALESCE(contract_no, '')) COLLATE utf8mb4_general_ci IN :contract_ids"
                ).bindparams(bindparam("contract_ids", expanding=True)),
                {"contract_ids": contract_ids},
            ).fetchall()
            serials: list[str] = []
            seen_serials: set[str] = set()
            for row in unit_serial_rows:
                for value in row:
                    sn = str(value or "").strip()
                    if not sn or sn in seen_serials:
                        continue
                    seen_serials.add(sn)
                    serials.append(sn)
            if serials:
                set_sql = "`占用订单号` = :order_id"
                if _table_has_column(conn, "finished_goods_data", "订单号"):
                    set_sql += ", `订单号` = :order_id"
                fg_ret = conn.execute(
                    text(
                        f"UPDATE finished_goods_data SET {set_sql} "
                        "WHERE TRIM(COALESCE(`流水号`, '')) IN :serials "
                        "AND TRIM(COALESCE(`状态`, '')) <> '已出库' "
                        "AND (COALESCE(TRIM(`占用订单号`), '') = '' OR TRIM(`占用订单号`) = :order_id)"
                    ).bindparams(bindparam("serials", expanding=True)),
                    {"serials": serials, "order_id": order_id},
                )
                finished_goods_rows = int(fg_ret.rowcount or 0)

        plan_import_rows = 0
        if _table_has_column(conn, "plan_import", "合同号"):
            _ensure_plan_import_order_column(conn)
            import_conflicts = conn.execute(
                text(
                    "SELECT DISTINCT `合同号`, `订单号` FROM plan_import "
                    "WHERE TRIM(COALESCE(`合同号`, '')) COLLATE utf8mb4_general_ci IN :contract_ids "
                    "AND COALESCE(TRIM(`订单号`), '') <> '' "
                    "AND TRIM(`订单号`) <> :order_id"
                ).bindparams(bindparam("contract_ids", expanding=True)),
                {"contract_ids": contract_ids, "order_id": order_id},
            ).fetchall()
            if import_conflicts:
                conflict_contract = str(import_conflicts[0][0] or "").strip()
                conflict_order = str(import_conflicts[0][1] or "").strip()
                raise HTTPException(status_code=422, detail=f"合同 {conflict_contract} 已绑定其他订单 {conflict_order}")

            import_ret = conn.execute(
                text(
                    "UPDATE plan_import SET `订单号` = :order_id "
                    "WHERE TRIM(COALESCE(`合同号`, '')) COLLATE utf8mb4_general_ci IN :contract_ids "
                    "AND (COALESCE(TRIM(`订单号`), '') = '' OR TRIM(`订单号`) = :order_id)"
                ).bindparams(bindparam("contract_ids", expanding=True)),
                {"contract_ids": contract_ids, "order_id": order_id},
            )
            plan_import_rows = int(import_ret.rowcount or 0)

    return {"units": int(unit_ret.rowcount or 0), "plan_import": plan_import_rows, "finished_goods_data": finished_goods_rows}


def _link_contracts_to_order(contract_ids: list[str], order_id: str, status: str | None = "已转订单") -> int:
    if not contract_ids:
        return 0
    
    with get_engine().begin() as conn:
        # 1. 检查是否存在冲突
        existing = conn.execute(
            text(
                "SELECT `合同号`, `订单号` FROM factory_plan "
                "WHERE TRIM(COALESCE(`合同号`, '')) COLLATE utf8mb4_general_ci IN :cids "
                "AND COALESCE(TRIM(`订单号`), '') <> '' AND TRIM(`订单号`) <> :oid"
            ).bindparams(bindparam("cids", expanding=True)),
            {"cids": contract_ids, "oid": order_id}
        ).fetchall()
        
        if existing:
            conflict_contract = str(existing[0][0] or "").strip()
            conflict_order = str(existing[0][1] or "").strip()
            raise HTTPException(status_code=422, detail=f"合同 {conflict_contract} 已绑定其他订单 {conflict_order}")
            
        # 2. 直接使用 SQL UPDATE 更新状态和订单号，避免全表覆盖导致其他合同丢失
        set_status = ""
        params = {"oid": order_id, "cids": contract_ids}
        if status:
            set_status = ", `状态` = :status"
            params["status"] = status
            
        ret = conn.execute(
            text(f"UPDATE factory_plan SET `订单号` = :oid {set_status} "
                 "WHERE TRIM(COALESCE(`合同号`, '')) COLLATE utf8mb4_general_ci IN :cids").bindparams(bindparam("cids", expanding=True)),
            params
        )
        updated_count = int(ret.rowcount or 0)

    # 3. 清理缓存
    import crud.planning
    if hasattr(crud.planning.get_factory_plan, "cache_clear"):
        crud.planning.get_factory_plan.cache_clear()
    if hasattr(crud.planning.get_factory_plan_v2, "cache_clear"):
        crud.planning.get_factory_plan_v2.cache_clear()
    
    _sync_order_to_units_and_import(contract_ids, str(order_id))
    _occupy_inventory_for_order(contract_ids, str(order_id))
    return updated_count


def _validate_contracts_available(contract_ids: list[str], order_id: str) -> None:
    if not contract_ids:
        return
    df_plan = get_factory_plan()
    if df_plan.empty:
        raise HTTPException(status_code=422, detail="未找到可绑定的合同")
    mask = df_plan["合同号"].astype(str).isin(contract_ids)
    if not mask.any():
        raise HTTPException(status_code=422, detail="未找到可绑定的合同")
    existing = df_plan.loc[mask, "订单号"].fillna("").astype(str).str.strip()
    conflict = existing[(existing != "") & (existing != str(order_id))]
    if not conflict.empty:
        raise HTTPException(status_code=422, detail="所选合同中存在已绑定其他订单的记录")


def _get_order_contract_machine_rows(order_id: str) -> pd.DataFrame:
    order_id = str(order_id).strip()
    plan_df = get_factory_plan()
    contract_rows = plan_df[plan_df["订单号"].astype(str).str.strip() == order_id].copy() if not plan_df.empty else pd.DataFrame()
    contract_ids = sorted({
        str(x).strip()
        for x in contract_rows.get("合同号", pd.Series(dtype=str)).tolist()
        if str(x).strip()
    })

    inv_df = get_data()
    if inv_df.empty:
        inv_df = pd.DataFrame(columns=["流水号", "合同号", "占用订单号", "状态", "机型"])
    for col in ["流水号", "合同号", "占用订单号", "状态", "机型", "批次号", "客户", "代理商", "合同备注"]:
        if col not in inv_df.columns:
            inv_df[col] = ""

    linked_rows = pd.DataFrame(columns=inv_df.columns)
    if contract_ids:
        linked_rows = inv_df[inv_df["合同号"].astype(str).str.strip().isin(contract_ids)].copy()

    # 补充：按订单所需机型，额外拉取库存中尚未被任何订单占用的空闲机台。
    # 不限于合同号匹配，没有合同号的空闲机台也可以被配货。
    needed_models: set[str] = set()
    if not contract_rows.empty:
        needed_models = {
            str(x).strip()
            for x in contract_rows.get("机型", pd.Series(dtype=str)).tolist()
            if str(x).strip()
        }
    else:
        # 兜底：factory_plan 中查不到关联合同时，从 sales_orders 的需求文本提取机型
        orders_df = get_orders()
        order_match = orders_df[orders_df["订单号"].astype(str).str.strip() == order_id]
        if not order_match.empty:
            demand_text = str(order_match.iloc[0].get("需求机型", "") or "")
            needed_models = {m for m in _extract_models_from_demand_text(demand_text) if m}
    if needed_models:
        model_rows = inv_df[
            inv_df["机型"].astype(str).str.strip().isin(needed_models)
            & (inv_df["占用订单号"].astype(str).str.strip() == "")
            & (inv_df["状态"].astype(str).str.strip() != "已出库")
        ].copy()
        linked_rows = pd.concat([linked_rows, model_rows], ignore_index=True).drop_duplicates(subset=["流水号"], keep="first")

    occupied_rows = inv_df[inv_df["占用订单号"].astype(str).str.strip() == order_id].copy()
    rows = pd.concat([linked_rows, occupied_rows], ignore_index=True).drop_duplicates(subset=["流水号"], keep="first")

    expected_counts: dict[tuple[str, str], int] = {}
    expected_notes: dict[tuple[str, str], str] = {}
    if not contract_rows.empty:
        for _, row in contract_rows.iterrows():
            cid = str(row.get("合同号", "") or "").strip()
            model = str(row.get("机型", "") or "").strip()
            if not cid or not model:
                continue
            try:
                qty = int(float(row.get("排产数量", 0) or 0))
            except Exception:
                qty = 0
            expected_counts[(cid, model)] = expected_counts.get((cid, model), 0) + max(0, qty)
            note = str(row.get("备注", "") or "").strip()
            if note:
                expected_notes[(cid, model)] = note
    else:
        # 兜底：factory_plan 没有关联合同时，从 sales_orders 取需求数量
        orders_df = get_orders()
        order_match = orders_df[orders_df["订单号"].astype(str).str.strip() == order_id]
        if not order_match.empty:
            demand_text = str(order_match.iloc[0].get("需求机型", "") or "")
            total_qty = int(order_match.iloc[0].get("需求数量", 0) or 0)
            models = _extract_models_from_demand_text(demand_text)
            qty_per_model = max(1, total_qty // len(models)) if models else 0
            for model in models:
                expected_counts[(order_id, model)] = qty_per_model

    placeholders = []
    for (cid, model), qty in expected_counts.items():
        matched = rows[
            (rows["合同号"].astype(str).str.strip() == cid)
            & (rows["机型"].astype(str).str.strip() == model)
        ]
        for i in range(max(0, qty - len(matched))):
            placeholders.append({
                "流水号": "",
                "批次号": "",
                "机型": model,
                "状态": "未入库",
                "预计入库时间": "",
                "更新时间": "",
                "占用订单号": "",
                "客户": "",
                "代理商": "",
                "合同备注": expected_notes.get((cid, model), ""),
                "Location_Code": "",
                "合同号": cid,
                "_placeholder": f"{cid}-{model}-{i + 1}",
            })
    if placeholders:
        rows = pd.concat([rows, pd.DataFrame(placeholders)], ignore_index=True)
    return rows

@router.get("/")
def get_planning_data(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    status: str = Query(""),
    contract_id: str = Query(""),
):
    try:
        where_clauses = []
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if str(status).strip():
            where_clauses.append("`状态` = :status")
            params["status"] = str(status).strip()
        if str(contract_id).strip():
            where_clauses.append("`合同号` = :contract_id")
            params["contract_id"] = str(contract_id).strip()
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        count_sql = f"SELECT COUNT(*) AS total FROM factory_plan{where_sql}"
        data_sql = (
            "SELECT `id` AS `_idx`, `合同号`, `机型`, `排产数量`, `要求交期`, `状态`, `备注`, `客户名`, `代理商`, `指定批次/来源`, `订单号` "
            f"FROM factory_plan{where_sql} "
            "ORDER BY `id` DESC LIMIT :limit OFFSET :skip"
        )
        with get_engine().connect() as conn:
            total_df = pd.read_sql(text(count_sql), conn, params=params)
            total = int(total_df.iloc[0]["total"]) if not total_df.empty else 0
            df_plan = pd.read_sql(text(data_sql), conn, params=params)

        if "指定批次/来源" in df_plan.columns:
            df_plan["指定批次/来源"] = df_plan["指定批次/来源"].apply(parse_alloc_dict)
        df_plan = df_plan.where(df_plan.notnull(), None)
        return {"data": df_plan.to_dict(orient="records"), "total": total, "skip": skip, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders")
def get_sales_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    status: str = Query(""),
    keyword: str = Query(""),
):
    try:
        where_clauses = []
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if str(status).strip():
            where_clauses.append("`status` = :status")
            params["status"] = str(status).strip()
        if str(keyword).strip():
            where_clauses.append("(`订单号` LIKE :kw OR `客户名` LIKE :kw OR `代理商` LIKE :kw)")
            params["kw"] = f"%{str(keyword).strip()}%"
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        count_sql = f"SELECT COUNT(*) AS total FROM sales_orders{where_sql}"
        data_sql = (
            "SELECT `订单号`, `客户名`, `代理商`, `需求机型`, `需求数量`, "
            "DATE_FORMAT(`下单时间`, '%Y-%m-%d') AS `下单时间`, "
            "`备注`, `包装选项`, "
            "DATE_FORMAT(`发货时间`, '%Y-%m-%d') AS `发货时间`, "
            "`指定批次/来源`, `status`, `delete_reason` "
            "FROM sales_orders"
            f"{where_sql} "
            "ORDER BY sales_orders.`下单时间` DESC LIMIT :limit OFFSET :skip"
        )
        with get_engine().connect() as conn:
            total_df = pd.read_sql(text(count_sql), conn, params=params)
            total = int(total_df.iloc[0]["total"]) if not total_df.empty else 0
            df_orders = pd.read_sql(text(data_sql), conn, params=params)

        df_orders = _reconcile_completed_orders(df_orders)
        df_orders = df_orders.where(df_orders.notnull(), None)
        return {"data": df_orders.to_dict(orient="records"), "total": total, "skip": skip, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders")
def create_sales_order_api(
    payload: SalesOrderCreatePayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        _assert_models_in_dictionary(_extract_models_from_demand_text(str(payload.需求机型 or "")))
        df_orders = get_orders()
        order_id = f"SO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
        contract_ids = _clean_contract_ids(payload.contract_ids)
        _validate_contracts_available(contract_ids, order_id)
        new_row = {
            "订单号": order_id,
            "客户名": str(payload.客户名 or ""),
            "代理商": str(payload.代理商 or ""),
            "需求机型": str(payload.需求机型 or ""),
            "需求数量": int(payload.需求数量),
            "下单时间": datetime.now(),
            "备注": str(payload.备注 or ""),
            "包装选项": str(payload.包装选项 or ""),
            "发货时间": pd.to_datetime(payload.发货时间, errors="coerce") if payload.发货时间 else None,
            "指定批次/来源": {},
            "status": "active",
            "delete_reason": "",
        }
        df_orders = pd.concat([df_orders, pd.DataFrame([new_row])], ignore_index=True)
        save_orders(df_orders)
        linked_count = _link_contracts_to_order(contract_ids, order_id) if contract_ids else 0
        append_audit_log(
            module="销售下单",
            action_type="新增",
            biz_type="订单",
            content=(
                f"创建订单：{order_id}；客户：{payload.客户名}；"
                f"需求机型：{str(payload.需求机型 or '').strip() or '未填写'}；"
                f"需求数量：{int(payload.需求数量)}"
                + (f"；绑定合同：{', '.join(contract_ids)}" if contract_ids else "")
            ),
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": "订单创建成功", "order_id": order_id, "linked_contract_count": linked_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建订单失败: {e}")


def _clear_sandbox_units_by_order(order_id: str) -> None:
    """
    【缺口2补全】订单删除时，清空沙盘 units 表中该订单关联卡片的合同字段。
    通过 sales_id = order_id 匹配（_sync_order_to_units_and_import 在创建订单时写入）。
    只清空 Predicted 状态的批次中的卡片，已下达/生产中的卡片不动。
    失败不抛异常（fire-and-forget），避免阻塞主流程。
    """
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text("""
                    UPDATE units u
                    JOIN batches b ON b.batch_id = u.batch_id
                    SET u.contract_no = NULL,
                        u.customer    = NULL,
                        u.dealer_name = NULL,
                        u.dealer_id   = NULL,
                        u.due_date    = NULL,
                        u.sales_id    = NULL,
                        u.order_remark = NULL,
                        u.is_locked   = 0,
                        u.locked_by   = NULL,
                        u.locked_at   = NULL,
                        u.updated_at  = NOW()
                    WHERE u.sales_id = :order_id
                      AND b.status = 'Predicted'
                """),
                {"order_id": order_id}
            )
    except Exception as e:
        print(f"Warning: _clear_sandbox_units_by_order failed for order {order_id}: {e}")


def _sync_contract_fields_to_units(
    contract_id: str,
    customer: str = "",
    dealer_name: str = "",
    due_date: str = "",
    model_type: str = "",
    order_remark: str = "",
) -> None:
    """
    【缺口3补全】合同编辑后局部更新沙盘 units 表中的卡片字段。
    通过 contract_no = contract_id 匹配，只更新 Predicted 批次中的卡片。
    失败不抛异常（fire-and-forget），避免阻塞主流程。
    """
    try:
        due_date_val = None
        if due_date:
            try:
                due_date_val = pd.to_datetime(due_date, errors="coerce")
                if pd.isna(due_date_val):
                    due_date_val = None
                else:
                    due_date_val = due_date_val.strftime("%Y-%m-%d")
            except Exception:
                due_date_val = None

        with get_engine().begin() as conn:
            conn.execute(
                text("""
                    UPDATE units u
                    JOIN batches b ON b.batch_id = u.batch_id
                    SET u.customer     = :customer,
                        u.dealer_name  = :dealer_name,
                        u.due_date     = :due_date,
                        u.order_remark = CASE
                            WHEN :order_remark != '' AND (:model_type = '' OR TRIM(COALESCE(u.model_type, '')) = :model_type) THEN :order_remark
                            ELSE u.order_remark
                        END,
                        u.updated_at   = NOW()
                    WHERE u.contract_no = :contract_id
                      AND b.status IN ('Predicted', 'Confirmed', 'In_Production')
                """),
                {
                    "customer": customer or None,
                    "dealer_name": dealer_name or None,
                    "due_date": due_date_val,
                    "model_type": model_type,
                    "order_remark": order_remark,
                    "contract_id": contract_id,
                }
            )
    except Exception as e:
        print(f"Warning: _sync_contract_fields_to_units failed for contract {contract_id}: {e}")



class UnitSyncPayload(BaseModel):
    contract_no: str
    old_model: str
    new_model: str
    order_remark: str
    customer: str = ""
    dealer_name: str = ""


# 内部专用路由，不带常规用户鉴权，内部校验 GO_INTERNAL_TOKEN
internal_router = APIRouter()


@internal_router.patch("/unit-sync")
def internal_sync_unit_api(payload: UnitSyncPayload, request: Request):
    """
    【缺口1补全】看板反向同步到主系统：当看板卡片修改备注或机型时，回写 factory_plan。
    """
    # 改进的内部令牌校验
    config_token = (GO_INTERNAL_TOKEN or "").strip()
    provided_token = (request.headers.get("X-Internal-Token") or "").strip()
    
    # 只有当配置了 Token 时才强制校验，防止本地开发环境无法运行
    if config_token and provided_token != config_token:
        raise HTTPException(status_code=403, detail="Unauthorized internal request")

    try:
        with get_engine().begin() as conn:
            columns = {
                str(row[0]).strip()
                for row in conn.execute(text("SHOW COLUMNS FROM factory_plan")).fetchall()
            }
            customer_col = "客户名" if "客户名" in columns else ("客户名称" if "客户名称" in columns else None)
            dealer_col = "代理商" if "代理商" in columns else None

            set_parts = ["`机型` = :new_model", "`备注` = :remark"]
            if customer_col:
                set_parts.append(f"`{customer_col}` = :customer")
            if dealer_col:
                set_parts.append(f"`{dealer_col}` = :dealer_name")
            set_sql = ",\n                        ".join(set_parts)

            # 更新 factory_plan 表
            # 注意：factory_plan 可能有多个相同合同+机型的行（如果拆分了），我们全部更新
            model_to_match = str(payload.old_model or "").strip() or str(payload.new_model or "").strip()
            conn.execute(
                text(f"""
                    UPDATE factory_plan 
                    SET {set_sql}
                    WHERE `合同号` = :contract_no
                      AND `机型` = :model_to_match
                """),
                {
                    "new_model": payload.new_model,
                    "remark": payload.order_remark,
                    "customer": payload.customer,
                    "dealer_name": payload.dealer_name,
                    "contract_no": payload.contract_no,
                    "model_to_match": model_to_match,
                }
            )
            print(
                f"[unit-sync] contract={payload.contract_no} model={model_to_match} "
                f"customer_col={customer_col or '-'} dealer_col={dealer_col or '-'}"
            )
        
        # 清理缓存，确保主系统刷新后能看到最新数据
        if hasattr(get_factory_plan, "cache_clear"):
            get_factory_plan.cache_clear()
        if hasattr(get_factory_plan_v2, "cache_clear"):
            get_factory_plan_v2.cache_clear()
            
        return {"status": "success"}
    except Exception as e:
        print(f"Internal Sync Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{order_id}")
def update_sales_order_api(
    order_id: str,
    payload: SalesOrderUpdatePayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        df_orders = get_orders()
        mask = df_orders["订单号"].astype(str) == str(order_id)
        if not mask.any():
            raise HTTPException(status_code=404, detail="订单不存在")

        updates = payload.model_dump(exclude_unset=True)
        if "需求机型" in updates:
            _assert_models_in_dictionary(_extract_models_from_demand_text(str(updates.get("需求机型") or "")))
        for key, value in updates.items():
            if key == "需求数量" and value is not None:
                df_orders.loc[mask, key] = int(value)
            elif key == "发货时间":
                df_orders.loc[mask, key] = pd.to_datetime(value, errors="coerce") if value else None
            else:
                df_orders.loc[mask, key] = "" if value is None else str(value)
        save_orders(df_orders)
        changed_fields = [k for k, v in updates.items() if v is not None]
        append_audit_log(
            module="销售下单",
            action_type="修改",
            biz_type="订单",
            content=f"修改订单：{order_id}；更新字段：{', '.join(changed_fields) or '无'}",
            user_id=current_user.get("username"),
            username=current_operator,
        )

        # 【缺口2补全】订单被软删除时，清空沙盘中该订单关联卡片的合同字段，防止幽灵卡片并释放物理库存占用
        if updates.get("status") == "deleted":
            _clear_sandbox_units_by_order(str(order_id))
            inv_df = get_data()
            allocated_sns = inv_df[(inv_df["占用订单号"].astype(str) == str(order_id)) & (inv_df["状态"] != "已出库")]["流水号"].tolist()
            if allocated_sns:
                revert_to_inbound(allocated_sns, reason=f"订单软删除-自动解绑-{order_id}", operator=current_operator)

        return {"message": "订单更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新订单失败: {e}")


@router.delete("/orders/{order_id}")
def hard_delete_sales_order_api(
    order_id: str,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        from crud.orders import get_orders, save_orders
        df_orders = get_orders()
        mask = df_orders["订单号"].astype(str) == str(order_id)
        if not mask.any():
            raise HTTPException(status_code=404, detail="订单不存在")

        # 【缺口2补全】彻底删除前先清空沙盘关联卡片，防止幽灵卡片并释放物理库存占用
        _clear_sandbox_units_by_order(str(order_id))
        inv_df = get_data()
        allocated_sns = inv_df[(inv_df["占用订单号"].astype(str) == str(order_id)) & (inv_df["状态"] != "已出库")]["流水号"].tolist()
        if allocated_sns:
            revert_to_inbound(allocated_sns, reason=f"订单彻底删除-自动解绑-{order_id}", operator=current_operator)

        df_orders = df_orders[~mask].copy()
        save_orders(df_orders)
        
        append_audit_log(
            module="销售下单",
            action_type="彻底删除",
            biz_type="订单",
            content=f"彻底删除订单：{order_id}",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": "订单已永久删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"彻底删除订单失败: {e}")


@router.get("/orders/{order_id}/allocations")
def get_order_allocations_api(order_id: str):
    try:
        order_id = str(order_id).strip()
        if not order_id:
            raise HTTPException(status_code=422, detail="订单号不能为空")
        rows = _get_order_contract_machine_rows(order_id)
        rows = rows.where(rows.notnull(), None)
        return {"data": rows.to_dict(orient="records")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配货记录失败: {e}")


@router.post("/orders/{order_id}/allocate")
def allocate_order_inventory_api(
    order_id: str,
    payload: OrderAllocatePayload,
    request: Request = None,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        selected = [str(x).strip() for x in (payload.selected_serial_nos or []) if str(x).strip()]
        if not selected:
            raise HTTPException(status_code=422, detail="请先选择要配货的机台")

        orders_df = get_orders()
        hit = orders_df[orders_df["订单号"].astype(str) == str(order_id)]
        if hit.empty:
            raise HTTPException(status_code=404, detail="订单不存在")
        first = hit.iloc[0]
        customer = str(first.get("客户名", "") or "")
        agent = str(first.get("代理商", "") or "")
        candidate_rows = _get_order_contract_machine_rows(str(order_id))
        valid_sns = set(
            candidate_rows[
                (candidate_rows["流水号"].astype(str).str.strip() != "")
                & (candidate_rows["状态"].astype(str).str.strip() != "已出库")
                & (
                    (candidate_rows["占用订单号"].astype(str).str.strip() == "")
                    | (candidate_rows["占用订单号"].astype(str).str.strip() == str(order_id))
                )
            ]["流水号"].astype(str).str.strip().tolist()
        )
        invalid = [sn for sn in selected if sn not in valid_sns]
        if invalid:
            raise HTTPException(status_code=422, detail=f"所选机台不属于该订单绑定合同，或已不可配货: {', '.join(invalid[:10])}")
        allocate_inventory(str(order_id), customer, agent, selected, operator=current_operator)
        append_audit_log(
            module="订单配货",
            action_type="配货",
            biz_type="订单",
            content=f"为订单 {order_id} 配货 {len(selected)} 台机台；流水号：{', '.join(selected[:10])}",
            user_id=_user_id_from_context(current_user),
            username=current_operator,
        )
        return {"message": f"配货成功，已锁定 {len(selected)} 台机台"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配货失败: {e}")


@router.post("/orders/{order_id}/complete-allocation")
def complete_order_allocation_api(
    order_id: str,
    request: Request = None,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        order_id = str(order_id).strip()
        if not order_id:
            raise HTTPException(status_code=422, detail="订单号不能为空")

        orders_df = get_orders()
        hit = orders_df[orders_df["订单号"].astype(str).str.strip() == order_id]
        if hit.empty:
            raise HTTPException(status_code=404, detail="订单不存在")
        order_idx = hit.index[0]
        current_status = str(orders_df.at[order_idx, "status"] or "active")
        if current_status == "ready":
            return {"message": "配货已完成", "completed": True, "logged": 0}

        demand_counts = _parse_order_demand_counts(hit.iloc[0])
        if not demand_counts:
            raise HTTPException(status_code=422, detail="订单需求机型为空，无法完成配货")

        inv_df = get_data()
        if inv_df.empty:
            raise HTTPException(status_code=422, detail="配货未完成：未找到已配机台")
        for col in ["流水号", "机型", "状态", "占用订单号"]:
            if col not in inv_df.columns:
                inv_df[col] = ""

        allocated_df = inv_df[
            (inv_df["占用订单号"].astype(str).str.strip() == order_id)
            & (inv_df["状态"].astype(str).str.strip() != "已出库")
            & (inv_df["流水号"].astype(str).str.strip() != "")
        ].copy()
        allocated_counts: dict[str, int] = {}
        for _, row in allocated_df.iterrows():
            model = str(row.get("机型", "") or "").strip()
            if model:
                allocated_counts[model] = allocated_counts.get(model, 0) + 1

        missing: list[str] = []
        for model, need in demand_counts.items():
            allocated = allocated_counts.get(model, 0)
            if allocated < need:
                missing.append(f"{model} 缺少 {need - allocated} 台")
        if missing:
            raise HTTPException(status_code=422, detail=f"配货未完成：{'；'.join(missing)}")

        serials = allocated_df["流水号"].astype(str).str.strip().tolist()
        if serials:
            from database import get_engine
            from sqlalchemy import text, bindparam
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            try:
                with get_engine().begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE finished_goods_data
                            SET 状态 = '待发货',
                                更新时间 = :now
                            WHERE 流水号 IN :sns AND 状态 != '已出库'
                        """).bindparams(bindparam("sns", expanding=True)),
                        {"now": now_str, "sns": serials}
                    )
            except Exception as ex:
                raise HTTPException(status_code=500, detail=f"更新机台状态为待发货失败: {ex}")
            append_log("配货自动入库", serials, operator=current_operator)

        orders_df.at[order_idx, "status"] = "ready"
        save_orders(orders_df)
        append_audit_log(
            module="订单配货",
            action_type="配货完成",
            biz_type="订单",
            content=f"订单 {order_id} 配货完成，记录配货自动入库 {len(serials)} 台；流水号：{', '.join(serials[:10])}",
            user_id=_user_id_from_context(current_user),
            username=current_operator,
        )
        return {"message": "配货完成，订单已满足", "completed": True, "logged": len(serials)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配货完成失败: {e}")


@router.post("/orders/{order_id}/release")
def release_order_inventory_api(
    order_id: str,
    payload: OrderReleasePayload,
    request: Request = None,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        order_id = str(order_id).strip()
        if not order_id:
            raise HTTPException(status_code=422, detail="订单号不能为空")

        inv_df = get_data()
        allocated_df = inv_df[
            (inv_df["占用订单号"].astype(str) == order_id)
            & (inv_df["状态"].astype(str) != "已出库")
        ]
        if allocated_df.empty:
            return {"message": "该订单当前没有可释放的配货机台", "released": 0}

        if payload.all:
            target_sns = allocated_df["流水号"].astype(str).tolist()
        else:
            selected = [str(x).strip() for x in (payload.selected_serial_nos or []) if str(x).strip()]
            if not selected:
                raise HTTPException(status_code=422, detail="请先选择要释放的机台")
            target_sns = allocated_df[allocated_df["流水号"].astype(str).isin(selected)]["流水号"].astype(str).tolist()
            if not target_sns:
                raise HTTPException(status_code=422, detail="所选机台不属于当前订单或已不可释放")

        revert_to_inbound(target_sns, reason=f"订单配货释放-{order_id}", operator=current_operator)
        orders_df = get_orders()
        hit = orders_df[orders_df["订单号"].astype(str).str.strip() == order_id]
        if not hit.empty:
            order_idx = hit.index[0]
            if str(orders_df.at[order_idx, "status"] or "active") == "ready":
                orders_df.at[order_idx, "status"] = "active"
                save_orders(orders_df)
        append_audit_log(
            module="订单配货",
            action_type="释放",
            biz_type="订单",
            content=f"释放订单 {order_id} 已配机台 {len(target_sns)} 台；流水号：{', '.join(target_sns[:10])}",
            user_id=_user_id_from_context(current_user),
            username=current_operator,
        )
        return {"message": f"已释放 {len(target_sns)} 台机台", "released": len(target_sns)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"释放配货失败: {e}")


@router.post("/contract/{contract_id}/status")
def update_contract_status(
    contract_id: str,
    payload: StatusPayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        new_status = str(payload.status or "").strip()
        if not new_status:
            raise HTTPException(status_code=422, detail="status 不能为空")
        with get_engine().begin() as conn:
            result = conn.execute(
                text("UPDATE factory_plan SET `状态` = :status WHERE `合同号` = :cid"),
                {"status": new_status, "cid": str(contract_id)},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="合同不存在")
            
            if new_status == "已取消":
                conn.execute(
                    text("DELETE FROM production_queue WHERE contract_no = :cid AND status = 'Waiting'"),
                    {"cid": str(contract_id)}
                )
                conn.execute(
                    text("UPDATE rush_order_queue SET status = 'deleted' WHERE contract_no = :cid AND status = 'pending'"),
                    {"cid": str(contract_id)}
                )
                conn.execute(
                    text("""
                        UPDATE units
                        SET contract_no = NULL,
                            customer = NULL,
                            dealer_name = NULL,
                            sales_id = NULL,
                            due_date = NULL,
                            order_remark = NULL,
                            is_locked = 0
                        WHERE contract_no = :cid
                    """),
                    {"cid": str(contract_id)}
                )
                
        get_factory_plan.cache_clear()
        get_factory_plan_v2.cache_clear()
        if new_status == "已取消":
            _trigger_sandbox_recompute_sync(current_user)
        append_audit_log(
            module="合同管理",
            action_type="更新状态",
            biz_type="合同",
            content=f"合同 {contract_id} 状态更新为：{new_status}" + ("（已同步清空沙盘所有状态批次卡片及排产队列，并触发预测沙盒重算）" if new_status == "已取消" else ""),
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": f"合同状态已更新为 {new_status}" + ("，对应沙盘卡片及队列已同步清理，预测沙盒已同步重算" if new_status == "已取消" else "")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"状态更新失败: {e}")


@router.post("/contract/{contract_id}/link-order")
def link_contract_to_order(
    contract_id: str,
    payload: LinkOrderPayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        order_id = str(payload.order_id or "").strip()
        if not order_id:
            raise HTTPException(status_code=422, detail="订单号不能为空")

        # 验证订单号是否存在
        orders_df = get_orders()
        if orders_df.empty or order_id not in orders_df["订单号"].values:
            raise HTTPException(status_code=404, detail=f"订单号 {order_id} 不存在")

        df_plan = get_factory_plan()
        mask = df_plan["合同号"].astype(str) == str(contract_id)
        if not mask.any():
            raise HTTPException(status_code=404, detail="合同不存在")

        existing = df_plan.loc[mask, "订单号"].fillna("").astype(str).str.strip()
        conflict = existing[(existing != "") & (existing != order_id)]
        if not conflict.empty:
            raise HTTPException(status_code=400, detail=f"合同已关联订单 {conflict.iloc[0]}，请先解除关联")

        _link_contracts_to_order([str(contract_id)], order_id)
        append_audit_log(
            module="合同管理",
            action_type="关联订单",
            biz_type="合同",
            content=f"合同 {contract_id} 关联订单：{order_id}",
            user_id=current_user.get("username"),
            username=current_operator,
        )

        return {"message": f"已成功将合同 {contract_id} 与订单 {order_id} 关联"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"关联订单失败: {e}")


def _process_contracts_batch(
    add_list: List[Dict[str, Any]],
    rush_source_rows: List[Dict[str, Any]],
    save_mode: str,
    is_rush: bool,
    user_ctx: dict,
    operator: str,
    background_tasks=None,
) -> dict:
    """Core contract creation logic, reusable from multiple endpoints."""
    if not add_list:
        raise HTTPException(status_code=422, detail="没有可新增记录（可能都已存在或字段不完整）")

    df_plan = get_factory_plan()
    now_status = "已规划" if save_mode == "spot" else "待规划"

    # Filter out duplicates within this batch call
    clean_add_list: List[Dict[str, Any]] = []
    clean_rush_rows: List[Dict[str, Any]] = []
    existed = 0
    for i, item in enumerate(add_list):
        cid = str(item["合同号"])
        model = str(item["机型"])
        dup_mask = (df_plan["合同号"].astype(str) == cid) & (df_plan["机型"].astype(str) == model)
        if dup_mask.any():
            existed += 1
            continue
        item["状态"] = now_status
        clean_add_list.append(item)
        if i < len(rush_source_rows):
            clean_rush_rows.append(rush_source_rows[i])

    if not clean_add_list:
        raise HTTPException(status_code=422, detail="没有可新增记录（可能都已存在或字段不完整）")

    df_plan = pd.concat([df_plan, pd.DataFrame(clean_add_list)], ignore_index=True)
    save_factory_plan(df_plan)

    if save_mode == "sandbox" and not is_rush and background_tasks:
        background_tasks.add_task(_trigger_sandbox_recompute_sync, user_ctx)

    rush_q_rows = clean_rush_rows if (is_rush and save_mode == "sandbox") else []
    rush_created = _insert_rush_order_queue(
        rush_q_rows,
        created_by=user_ctx.get("username") or operator,
    )
    rush_auto_inserted = _auto_insert_rush_orders(rush_q_rows, user_ctx, operator)

    added_contract_ids = list(set([str(item["合同号"]) for item in clean_add_list]))
    contract_ids_str = "、".join(added_contract_ids)

    if save_mode == "spot" and added_contract_ids:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "UPDATE rush_order_queue SET `status` = 'deleted', `updated_by` = :updated_by "
                    "WHERE TRIM(COALESCE(`contract_no`, '')) COLLATE utf8mb4_general_ci IN :cids "
                    "AND `status` = 'pending'"
                ).bindparams(bindparam("cids", expanding=True)),
                {
                    "cids": added_contract_ids,
                    "updated_by": str(user_ctx.get("username") or operator or ""),
                },
            )

    append_audit_log(
        module="合同管理",
        action_type="批量录入",
        biz_type="合同",
        content=f"批量录入合同 {len(clean_add_list)} 条（合同号：{contract_ids_str}）；跳过重复 {existed} 条；急单自动入沙盘 {rush_auto_inserted} 条",
        user_id=user_ctx.get("username"),
        username=operator,
    )
    return {
        "message": f"批量录入完成，新增 {len(clean_add_list)} 条，跳过重复 {existed} 条",
        "inserted": len(clean_add_list),
        "skipped": existed,
        "rush_created": rush_created,
        "rush_auto_inserted": rush_auto_inserted,
        "save_mode": save_mode,
        "contract_ids": added_contract_ids,
    }


@router.post("/contracts/batch-create")
def create_contracts_batch(
    payload: BatchContractCreatePayload,
    request: Request,
    background_tasks: BackgroundTasks,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        save_mode = str(payload.save_mode or "sandbox").strip().lower()
        if save_mode not in {"sandbox", "spot"}:
            raise HTTPException(status_code=422, detail="save_mode 仅支持 sandbox 或 spot")
        rows = payload.rows or []
        if not rows:
            raise HTTPException(status_code=422, detail="请至少提供 1 条合同记录")
        _assert_models_in_dictionary([str(item.机型 or "").strip() for item in rows])

        add_list: List[Dict[str, Any]] = []
        rush_source_rows: List[Dict[str, Any]] = []
        for item in rows:
            cid = str(item.合同号 or "").strip()
            customer = str(item.客户名 or "").strip()
            model = str(item.机型 or "").strip()
            due = str(item.要求交期 or "").strip()
            if not cid or not customer or not model or not due:
                continue
            qty = int(item.排产数量)
            add_list.append(
                {
                    "合同号": cid,
                    "机型": model,
                    "排产数量": qty,
                    "要求交期": due,
                    "状态": "",  # filled by _process_contracts_batch
                    "备注": str(item.备注 or "").strip(),
                    "客户名": customer,
                    "代理商": str(item.代理商 or "").strip(),
                    "指定批次/来源": {},
                    "订单号": "",
                }
            )
            rush_source_rows.append(
                {
                    "contract_no": cid,
                    "customer": customer,
                    "dealer_name": str(item.代理商 or "").strip(),
                    "model_type": model,
                    "due_date": due,
                    "qty": qty,
                    "remark": str(item.备注 or "").strip(),
                }
            )

        result = _process_contracts_batch(
            add_list=add_list,
            rush_source_rows=rush_source_rows,
            save_mode=save_mode,
            is_rush=bool(payload.is_rush),
            user_ctx=current_user,
            operator=current_operator,
            background_tasks=background_tasks,
        )

        # 如果来自经销商订单，回写 contract_no
        dealer_order_no = str(payload.dealer_order_no or "").strip()
        if dealer_order_no and result.get("contract_ids"):
            from crud.dealer_orders import mark_dealer_order_contracted
            try:
                contract_no_str = "、".join(result["contract_ids"])
                mark_dealer_order_contracted(
                    dealer_order_no,
                    contract_no=contract_no_str,
                    operator=current_operator,
                )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to update dealer_order %s after contract creation: %s",
                    dealer_order_no, exc,
                )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量录入失败: {e}")


@router.put("/contract/{contract_id}")
def edit_contract(
    contract_id: str,
    payload: ContractEditPayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        if not payload.items:
            raise HTTPException(status_code=422, detail="至少保留一条机型明细")
        _assert_models_in_dictionary([str(item.机型 or "").strip() for item in payload.items])

        df_plan = get_factory_plan()
        target_mask = df_plan["合同号"].astype(str) == str(contract_id)
        if not target_mask.any():
            raise HTTPException(status_code=404, detail="合同不存在")

        existing = df_plan[target_mask]
        status_now = str(existing.iloc[0].get("状态", "待规划"))
        if status_now == "未下单":
            status_now = "待规划"
        order_id = str(existing.iloc[0].get("订单号", "") or "")

        # 删除旧行并重建
        df_plan = df_plan[~target_mask].copy()
        new_rows: List[Dict[str, Any]] = []
        for item in payload.items:
            model = str(item.机型 or "").strip()
            qty = int(item.排产数量)
            if not model:
                continue
            new_rows.append(
                {
                    "合同号": str(contract_id),
                    "机型": model,
                    "排产数量": qty,
                    "要求交期": str(payload.要求交期),
                    "状态": status_now,
                    "备注": str(item.备注 or ""),
                    "客户名": str(payload.客户名 or ""),
                    "代理商": str(payload.代理商 or ""),
                    "指定批次/来源": {},
                    "订单号": order_id,
                }
            )

        if not new_rows:
            raise HTTPException(status_code=422, detail="机型明细无有效数据")

        df_plan = pd.concat([df_plan, pd.DataFrame(new_rows)], ignore_index=True)
        save_factory_plan(df_plan)

        # 【缺口3补全】合同编辑后，局部同步沙盘中对应卡片的字段（交期/客户/代理商/备注）
        # 只更新 Predicted 批次中的卡片，不触碰已下达/生产中的卡片
        _sync_contract_fields_to_units(
            contract_id=str(contract_id),
            customer=str(payload.客户名 or ""),
            dealer_name=str(payload.代理商 or ""),
            due_date=str(payload.要求交期 or ""),
            model_type=str(new_rows[0].get("机型", "")) if new_rows else "",
            order_remark=str(new_rows[0].get("备注", "")) if new_rows else "",
        )

        append_audit_log(
            module="合同管理",
            action_type="编辑",
            biz_type="合同",
            content=f"编辑合同：{contract_id}；机型明细 {len(new_rows)} 条",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": "合同修改已保存"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合同编辑失败: {e}")


@router.get("/contract/{contract_id}/files")
def get_contract_files_api(contract_id: str):
    try:
        df = get_contract_files(contract_id)
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取附件失败: {e}")


@router.post("/contract/{contract_id}/files")
async def upload_contract_file_api(
    contract_id: str,
    file: UploadFile = File(...),
    customer_name: str = "",
    uploader_name: str = "",
    current_operator: str = Depends(get_current_operator_name),
):
    try:
        ok, msg = await asyncio.to_thread(
            save_contract_file,
            file,
            customer_name or str(contract_id),
            contract_id,
            uploader_name or current_operator or "API",
            True,
        )
        if not ok:
            raise HTTPException(status_code=422, detail=msg)
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传附件失败: {e}")


@router.delete("/contract/{contract_id}/files/{file_name}")
def delete_contract_file_api(
    contract_id: str,
    file_name: str,
    current_operator: str = Depends(get_current_operator_name),
):
    try:
        decoded_name = unquote(file_name)
        ok, msg = delete_contract_file(contract_id, decoded_name, operator=current_operator or "API")
        if not ok:
            raise HTTPException(status_code=422, detail=msg)
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除附件失败: {e}")


@router.get("/contract/{contract_id}/files/{file_name}/download")
def download_contract_file_api(contract_id: str, file_name: str):
    try:
        decoded_name = unquote(file_name)
        df = get_contract_files(contract_id)
        if df.empty:
            raise HTTPException(status_code=404, detail="附件不存在")
        hit = df[df["file_name"].astype(str) == decoded_name]
        if hit.empty:
            raise HTTPException(status_code=404, detail="附件不存在")
        rel_path = str(hit.iloc[0].get("file_path", "")).strip()
        if not rel_path:
            raise HTTPException(status_code=404, detail="附件路径无效")
        abs_path = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=404, detail="附件文件不存在")
        return FileResponse(path=abs_path, filename=decoded_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载附件失败: {e}")


@router.get("/contract/{contract_id}/files/{file_name}/preview")
def preview_contract_file_api(contract_id: str, file_name: str):
    try:
        decoded_name = unquote(file_name)
        df = get_contract_files(contract_id)
        if df.empty:
            raise HTTPException(status_code=404, detail="附件不存在")
        hit = df[df["file_name"].astype(str) == decoded_name]
        if hit.empty:
            raise HTTPException(status_code=404, detail="附件不存在")

        rel_path = str(hit.iloc[0].get("file_path", "")).strip()
        if not rel_path:
            raise HTTPException(status_code=404, detail="附件路径无效")
        abs_path = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=404, detail="附件文件不存在")

        ext = os.path.splitext(decoded_name)[1].lower()
        if ext in {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
            mime_map = {
                ".pdf": "application/pdf",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".webp": "image/webp",
            }
            with open(abs_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
            return {
                "type": "url",
                "url": f"data:{mime_map[ext]};base64,{encoded}",
                "ext": ext,
            }

        if ext == ".docx":
            try:
                import mammoth
            except ImportError:
                raise HTTPException(status_code=422, detail="服务端缺少 mammoth，暂不支持 DOCX 在线预览")
            with open(abs_path, "rb") as f:
                result = mammoth.convert_to_html(f)
            return {
                "type": "html",
                "html": result.value or "",
                "ext": ext,
            }

        if ext == ".doc":
            return {
                "type": "legacy-doc",
                "ext": ext,
                "message": "DOC 为旧版 Word 二进制格式，当前仅支持下载后用 Word/WPS 查看；DOCX 可在线预览。",
            }

        return {"type": "", "ext": ext, "message": "该文件类型暂不支持在线预览"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览附件失败: {e}")


@router.post("/contract/{contract_id}/save-plan")
def save_contract_plan(
    contract_id: str,
    payload: PlanSavePayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        if not payload.rows:
            raise HTTPException(status_code=422, detail="缺少规划数据")

        # 1. 采用 SQL 精准 UPDATE，避免依赖 get_factory_plan 丢失主键及全表重写
        with get_engine().begin() as conn:
            # 验证合同是否存在
            res = conn.execute(
                text("SELECT 1 FROM factory_plan WHERE `合同号` = :cid LIMIT 1"),
                {"cid": str(contract_id)}
            )
            if not res.fetchone():
                raise HTTPException(status_code=404, detail="合同不存在")

            for row_payload in payload.rows:
                idx = int(row_payload.row_index)
                alloc = {}
                for k, v in (row_payload.allocation or {}).items():
                    qty = int(v or 0)
                    if qty > 0:
                        alloc[str(k)] = qty
                alloc_json = json.dumps(alloc, ensure_ascii=False)
                
                # 更新指定批次和状态
                if payload.mark_to_planned:
                    conn.execute(
                        text("""
                            UPDATE factory_plan
                            SET `指定批次/来源` = :alloc,
                                `状态` = CASE WHEN `状态` = '待规划' THEN '已规划' ELSE `状态` END
                            WHERE id = :id AND `合同号` = :cid
                        """),
                        {"alloc": alloc_json, "id": idx, "cid": str(contract_id)}
                    )
                else:
                    # 核心改动：如果未全部分配（mark_to_planned 为 False），
                    # 且数据库中该行状态已是"已规划"，则将其回退为"待规划"
                    conn.execute(
                        text("""
                            UPDATE factory_plan
                            SET `指定批次/来源` = :alloc,
                                `状态` = CASE WHEN `状态` = '已规划' THEN '待规划' ELSE `状态` END
                            WHERE id = :id AND `合同号` = :cid
                        """),
                        {"alloc": alloc_json, "id": idx, "cid": str(contract_id)}
                    )
        
        # 2. 清理缓存，确保下一次读取获取到最新数据
        from crud.planning import get_factory_plan
        get_factory_plan.cache_clear()

        # 3. 同步写回 sales_orders 的指定批次/来源（保持原有逻辑）
        df_plan = get_factory_plan()
        contract_rows = df_plan[df_plan["合同号"].astype(str) == str(contract_id)]
        order_id = str(contract_rows.iloc[0].get("订单号", "") or "").strip() if not contract_rows.empty else ""
        
        if order_id:
            all_plans: Dict[str, Dict[str, int]] = {}
            for _, row in contract_rows.iterrows():
                model_name = str(row.get("机型", "")).strip()
                alloc_data = row.get("指定批次/来源", {})
                if isinstance(alloc_data, str):
                    alloc_data = parse_alloc_dict(alloc_data)
                if model_name and alloc_data:
                    all_plans[model_name] = alloc_data
            if all_plans:
                orders_df = get_orders()
                hit = orders_df["订单号"].astype(str) == order_id
                if hit.any():
                    orders_df.loc[hit, "指定批次/来源"] = [all_plans] * int(hit.sum())
                    save_orders(orders_df)

        append_audit_log(
            module="合同管理",
            action_type="保存规划",
            biz_type="合同",
            content=f"保存合同 {contract_id} 的规划，共 {len(payload.rows)} 行",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": "规划保存成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"规划保存失败: {e}")


@router.get("/export-production-history")
def export_production_history(sheet: str = "all"):
    """导出截至目前的所有排产数据（包括生产中和已完工的机台明细）为 Excel 格式，包含排产台账和跟踪单"""
    from collections import OrderedDict, defaultdict
    try:
        include_ledger = sheet in ("all", "ledger")
        include_tracking = sheet in ("all", "tracking")

        with get_engine().connect() as conn:
            if include_ledger:
                sql_ledger = """
                    SELECT 
                        phl.unit_id AS `机台ID`,
                        COALESCE(phl.production_line_name, '待排产队列') AS `产线`,
                        phl.batch_code AS `批次号`,
                        phl.model_type AS `机型`,
                        phl.contract_no AS `合同号`,
                        phl.customer AS `客户名`,
                        phl.dealer_name AS `经销商`,
                        CASE phl.status
                            WHEN 'Completed' THEN '已完工'
                            WHEN 'In_Production' THEN '生产中'
                            WHEN 'Cancelled' THEN '已撤销'
                            ELSE phl.status
                        END AS `状态`,
                        COALESCE(fgb.batch_inbound_date, b.expected_inbound_date, fg.`预计入库时间`) AS `预计入库时间`,
                        COALESCE(u.is_locked, 0) AS `锁定状态`,
                        phl.order_remark AS `备注`,
                        phl.scheduled_at AS `排产上线时间`,
                        phl.completed_at AS `完工时间`,
                        COALESCE(u.serial_no, u.forecast_serial_no) AS `流水号`
                    FROM production_history_ledger phl
                    LEFT JOIN units u ON u.unit_id = phl.unit_id
                    LEFT JOIN batches b ON (b.batch_code COLLATE utf8mb4_general_ci = phl.batch_code COLLATE utf8mb4_general_ci AND phl.batch_code <> '') 
                        OR b.batch_id COLLATE utf8mb4_general_ci = SUBSTRING_INDEX(phl.unit_id, '-', 5) COLLATE utf8mb4_general_ci
                    LEFT JOIN (
                        SELECT `批次号` AS batch_code, MIN(`预计入库时间`) AS batch_inbound_date 
                        FROM finished_goods_data 
                        WHERE TRIM(COALESCE(`批次号`, '')) <> '' 
                        GROUP BY `批次号`
                    ) fgb ON TRIM(COALESCE(fgb.batch_code, '')) COLLATE utf8mb4_general_ci = TRIM(COALESCE(b.batch_code, '')) COLLATE utf8mb4_general_ci
                    LEFT JOIN finished_goods_data fg ON fg.`流水号` COLLATE utf8mb4_general_ci = COALESCE(u.serial_no, u.forecast_serial_no) COLLATE utf8mb4_general_ci
                    WHERE phl.status IN ('In_Production', 'Completed')
                    ORDER BY phl.scheduled_at DESC, phl.id DESC
                """
                df_ledger = pd.read_sql(text(sql_ledger), conn)
                records = df_ledger.to_dict('records')
            else:
                records = []

            if include_tracking:
                sql_ledger_for_t = """
                    SELECT 
                        phl.unit_id AS `机台ID`,
                        phl.batch_code AS `批次号`,
                        phl.model_type AS `机型`,
                        phl.order_remark AS `备注`,
                        COALESCE(u.serial_no, u.forecast_serial_no) AS `流水号`
                    FROM production_history_ledger phl
                    LEFT JOIN units u ON u.unit_id = phl.unit_id
                    LEFT JOIN batches b ON (b.batch_code COLLATE utf8mb4_general_ci = phl.batch_code COLLATE utf8mb4_general_ci AND phl.batch_code <> '') 
                        OR b.batch_id COLLATE utf8mb4_general_ci = SUBSTRING_INDEX(phl.unit_id, '-', 5) COLLATE utf8mb4_general_ci
                    WHERE phl.status IN ('In_Production', 'Completed')
                      AND b.status IN ('Confirmed', 'In_Production')
                """
                df_ledger_for_t = pd.read_sql(text(sql_ledger_for_t), conn)
                records_for_t = df_ledger_for_t.to_dict('records')

                sql_pending = """
                    SELECT 
                        u.unit_id AS `机台ID`,
                        '待排产队列' AS `产线`,
                        COALESCE(b.batch_code, '-') AS `批次号`,
                        u.model_type AS `机型`,
                        u.contract_no AS `合同号`,
                        u.customer AS `客户名`,
                        u.dealer_name AS `经销商`,
                        '待排产' AS `状态`,
                        b.expected_inbound_date AS `预计入库时间`,
                        COALESCE(u.is_locked, 0) AS `锁定状态`,
                        u.order_remark AS `备注`,
                        u.created_at AS `排产上线时间`,
                        NULL AS `完工时间`,
                        COALESCE(u.serial_no, u.forecast_serial_no) AS `流水号`
                    FROM units u
                    LEFT JOIN batches b ON b.batch_id = u.batch_id
                    WHERE u.status = 'Pending'
                      AND b.status IN ('Confirmed', 'In_Production')
                    ORDER BY u.created_at DESC, u.unit_id DESC
                """
                df_pending = pd.read_sql(text(sql_pending), conn)
                records_pending = df_pending.to_dict('records')
            else:
                records_for_t = []
                records_pending = []

        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = Workbook()

        # 创建 Sheet
        if include_ledger and include_tracking:
            ws = wb.active
            ws.title = "排产台账"
            ws2 = wb.create_sheet(title="跟踪单")
        elif include_ledger:
            ws = wb.active
            ws.title = "排产台账"
        elif include_tracking:
            ws2 = wb.active
            ws2.title = "跟踪单"

        # 样式定义
        header_fill = PatternFill(start_color="5C765C", end_color="5C765C", fill_type="solid")
        header_font = Font(name="宋体", size=11, bold=True, color="FFFFFF")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_border = Border(
            left=Side(style='thin', color='D3D3D3'),
            right=Side(style='thin', color='D3D3D3'),
            top=Side(style='thin', color='D3D3D3'),
            bottom=Side(style='thin', color='D3D3D3')
        )
        green_fill = PatternFill(start_color="EAF2E8", end_color="EAF2E8", fill_type="solid")
        orange_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

        # 辅助宽度计算函数
        def get_display_width(s):
            width = 0
            for char in s:
                if ord(char) > 127:
                    width += 2
                else:
                    width += 1
            return width

        def format_cell_value(model_type, remark, qty, target_width=20):
            prefix = f"{model_type} {remark}" if remark else model_type
            w = get_display_width(prefix)
            spaces = max(2, target_width - w)
            return prefix + " " * spaces + str(qty)

        # ------------------ 填充 Sheet 1: 排产台账 ------------------
        if include_ledger:
            model_columns = ["300", "400", "500", "600", "7055", "8055", "8060"]

            batches = OrderedDict()
            for r in records:
                batch_code = str(r.get("批次号") or "").strip()
                if not batch_code:
                    batch_code = "-"
                if batch_code not in batches:
                    batches[batch_code] = {
                        "batch_code": batch_code,
                        "units": [],
                        "due_dates": set()
                    }
                batches[batch_code]["units"].append(r)
                due_date = r.get("预计入库时间")
                if due_date and str(due_date).strip() not in ("", None, "-", "None", "NaT"):
                    batches[batch_code]["due_dates"].add(due_date)

            ws.views.sheetView[0].showGridLines = True
            headers = ["批次号"] + model_columns + ["合计", "预计入库时间"]
            ws.append(headers)

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_alignment

            start_row = 2
            total_cols = len(headers)

            sorted_batches = sorted(batches.items(), key=lambda x: (x[0] == "-", x[0]))
            for batch_code, batch in sorted_batches:
                unique_pairs = []
                pair_qty = defaultdict(int)
                for unit in batch["units"]:
                    orig_model = str(unit.get("机型") or "").strip()
                    remark = str(unit.get("备注") or "").strip()
                    if remark in ("None", "none", "null", "NULL"):
                        remark = ""
                    pair = (orig_model, remark)
                    if pair_qty[pair] == 0:
                        unique_pairs.append(pair)
                    pair_qty[pair] += 1

                matched_by_col = defaultdict(list)
                special_pairs = []
                for pair in unique_pairs:
                    orig_model, remark = pair
                    combined = (orig_model + remark).upper()
                    matched_col = None
                    for series in model_columns:
                        if series in combined:
                            matched_col = series
                            break
                    if matched_col:
                        matched_by_col[matched_col].append(pair)
                    else:
                        special_pairs.append(pair)

                col_assigned_count = {col: len(matched_by_col[col]) for col in model_columns}
                for pair in special_pairs:
                    best_col = min(model_columns, key=lambda c: col_assigned_count[c])
                    matched_by_col[best_col].append(pair)
                    col_assigned_count[best_col] += 1

                entries_by_model = {}
                for col_key in model_columns:
                    entries = []
                    for orig_model, remark in matched_by_col[col_key]:
                        qty = pair_qty[(orig_model, remark)]
                        entries.append(format_cell_value(orig_model, remark, qty, target_width=20))
                    entries_by_model[col_key] = entries

                max_rows = max(len(entries) for entries in entries_by_model.values())
                if max_rows == 0:
                    max_rows = 1

                end_row = start_row + max_rows - 1

                for r in range(start_row, end_row + 1):
                    for c in range(1, total_cols + 1):
                        cell = ws.cell(row=r, column=c)
                        cell.font = Font(name="宋体", size=10)
                        cell.border = thin_border
                        if c == total_cols:
                            cell.fill = orange_fill
                        else:
                            cell.fill = green_fill
                        if c == 1 or c == total_cols - 1 or c == total_cols:
                            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                        else:
                            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

                ws.cell(row=start_row, column=1).value = batch_code
                if end_row > start_row:
                    ws.merge_cells(start_row=start_row, start_column=1, end_row=end_row, end_column=1)

                for m_idx, m_type in enumerate(model_columns, start=2):
                    entries = entries_by_model[m_type]
                    for i, entry in enumerate(entries):
                        ws.cell(row=start_row + i, column=m_idx).value = entry
                    if len(entries) <= 1 and end_row > start_row:
                        ws.merge_cells(start_row=start_row, start_column=m_idx, end_row=end_row, end_column=m_idx)

                total_qty = len(batch["units"])
                ws.cell(row=start_row, column=total_cols - 1).value = total_qty
                if end_row > start_row:
                    ws.merge_cells(start_row=start_row, start_column=total_cols - 1, end_row=end_row, end_column=total_cols - 1)

                due_dates_list = []
                for d in batch["due_dates"]:
                    try:
                        dt = pd.to_datetime(d)
                        due_dates_list.append(f"预计{dt.year}. {dt.month}. {dt.day}")
                    except:
                        due_dates_list.append(str(d))
                due_date_str = ", ".join(sorted(due_dates_list)) if due_dates_list else "-"
                ws.cell(row=start_row, column=total_cols).value = due_date_str
                if end_row > start_row:
                    ws.merge_cells(start_row=start_row, start_column=total_cols, end_row=end_row, end_column=total_cols)

                start_row = end_row + 1

            for col in ws.columns:
                col_idx = col[0].column
                col_letter = get_column_letter(col_idx)
                if 2 <= col_idx <= 8:
                    ws.column_dimensions[col_letter].width = 24
                else:
                    max_len = 0
                    for cell in col:
                        val = str(cell.value or '')
                        w = get_display_width(val)
                        if w > max_len:
                            max_len = w
                    ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        # ------------------ 填充 Sheet 2: 跟踪单 ------------------
        if include_tracking:
            ws2.views.sheetView[0].showGridLines = True
            headers2 = ["生产批次", "型号", "生产编号"]
            ws2.append(headers2)

            for col_idx in range(1, len(headers2) + 1):
                cell = ws2.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_alignment

            combined_records = records_for_t + records_pending

            batches_tracking = defaultdict(list)
            for r in combined_records:
                b_code = str(r.get("批次号") or "").strip()
                if not b_code:
                    b_code = "-"
                batches_tracking[b_code].append(r)

            sorted_tracking_batches = sorted(batches_tracking.items(), key=lambda x: (x[0] == "-", x[0]))

            start_row_t = 2
            for b_code, b_units in sorted_tracking_batches:
                def sort_key(u):
                    sn = str(u.get("流水号") or "").strip()
                    uid = str(u.get("机台ID") or "").strip()
                    return (sn == "", sn, uid)

                sorted_units = sorted(b_units, key=sort_key)
                num_units = len(sorted_units)
                end_row_t = start_row_t + num_units - 1

                ws2.cell(row=start_row_t, column=1).value = b_code
                if end_row_t > start_row_t:
                    ws2.merge_cells(start_row=start_row_t, start_column=1, end_row=end_row_t, end_column=1)

                for i, u in enumerate(sorted_units):
                    row_idx = start_row_t + i
                    model = str(u.get("机型") or "").strip()
                    remark = str(u.get("备注") or "").strip()
                    if remark in ("None", "none", "null", "NULL"):
                        remark = ""

                    model_text = f"{model} {remark}" if remark else model
                    sn_text = str(u.get("流水号") or u.get("机台ID") or "").strip() or "-"

                    ws2.cell(row=row_idx, column=2).value = model_text
                    ws2.cell(row=row_idx, column=3).value = sn_text

                    for c in range(1, 4):
                        cell = ws2.cell(row=row_idx, column=c)
                        cell.font = Font(name="宋体", size=10)
                        cell.border = thin_border
                        cell.fill = green_fill
                        if c == 1 or c == 3:
                            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                        else:
                            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

                start_row_t = end_row_t + 1

            for col in ws2.columns:
                max_len = 0
                for cell in col:
                    val = str(cell.value or '')
                    w = get_display_width(val)
                    if w > max_len:
                        max_len = w
                col_letter = get_column_letter(col[0].column)
                ws2.column_dimensions[col_letter].width = max(max_len + 4, 12)

        import io
        from fastapi.responses import StreamingResponse

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        file_prefix = "production_history" if sheet != "tracking" else "production_tracking"
        headers = {
            "Content-Disposition": f"attachment; filename={file_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        }
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出排产数据失败: {e}")


class ExportExcelPayload(BaseModel):
    filename: str
    sheet_name: str
    headers: List[str]
    rows: List[List[Any]]


@router.post("/export-excel")
def export_excel(payload: ExportExcelPayload):
    """通用数据导出为 Excel xlsx 格式"""
    try:
        import io
        from fastapi.responses import StreamingResponse
        
        df = pd.DataFrame(payload.rows, columns=payload.headers)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=payload.sheet_name)
        output.seek(0)
        
        headers = {
            "Content-Disposition": f"attachment; filename={payload.filename}.xlsx"
        }
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出 Excel 失败: {e}")

