from io import BytesIO
from typing import List, Dict, Any
from datetime import datetime
import asyncio
import logging
import os
import requests
import pandas as pd
import re
import tempfile
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Query, Request, Response, BackgroundTasks
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from config import MACHINE_ARCHIVE_ABS_DIR, GO_SANDBOX_URL
from core.file_manager import audit_log
from crud.audit_logs import append_audit_log
from crud.dealer_orders import sync_dealer_order_statuses_by_sales_orders
from crud.cloud_sync_outbox import enqueue_cloud_sync_event, enqueue_wechat_batch_summary_sync
from crud.inventory import (
    INVENTORY_COLS,
    append_import_staging,
    delete_import_staging_by_serials,
    get_import_staging,
    get_warehouse_layout,
    reset_warehouse_layout,
    save_import_staging,
    save_warehouse_layout,
    archive_shipped_data,
)
from utils.cache_adapter import cache
from crud.logs import append_log
from crud.model_dictionary import find_disabled_models, is_model_enabled
from crud.orders import get_orders, revert_to_inbound, save_orders
from api.routes.auth import get_current_operator_name, get_current_user_context, get_current_user_token
from database import get_engine


router = APIRouter(dependencies=[Depends(get_current_user_token)])
MAX_INVENTORY_BULK_UPDATE_ROWS = 20000


def _assert_model_enabled(model_name: str) -> None:
    model = str(model_name or "").replace("(加高)", "").strip()
    if not model:
        raise HTTPException(status_code=422, detail="机型不能为空")
    if not is_model_enabled(model):
        raise HTTPException(status_code=422, detail=f"机型不在字典中或未启用: {model}")
def _sync_machine_edit_to_units(serial_nos: list[str]) -> int:
    sns = [str(x).strip() for x in serial_nos if str(x).strip()]
    if not sns:
        return 0
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE units u
                JOIN finished_goods_data fg 
                  ON TRIM(fg.`流水号`) = COALESCE(NULLIF(TRIM(u.serial_no), ''), NULLIF(TRIM(u.forecast_serial_no), ''))
                SET
                    u.order_remark = COALESCE(fg.`合同备注`, ''),
                    u.model_type = CASE
                        WHEN COALESCE(TRIM(fg.`机型`), '') <> '' THEN fg.`机型`
                        ELSE u.model_type
                    END,
                    u.updated_at = NOW()
                WHERE TRIM(COALESCE(u.serial_no, '')) IN :sns
                   OR TRIM(COALESCE(u.forecast_serial_no, '')) IN :sns
                """
            ).bindparams(bindparam("sns", expanding=True)),
            {"sns": sns},
        )
        return int(result.rowcount or 0)


class LayoutPayload(BaseModel):
    layout_id: str = "default"
    layout_json: Dict[str, Any]


class LayoutResetPayload(BaseModel):
    layout_id: str = "default"


class InboundSlotPayload(BaseModel):
    serial_no: str
    slot_code: str
    is_transfer: bool = False


class ImportStagingSavePayload(BaseModel):
    rows: List[Dict[str, Any]]


class ImportStagingDeletePayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)


class ShippingActionPayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)


class ArchiveBatchDeletePayload(BaseModel):
    file_names: List[str] = Field(default_factory=list)


class MachineInlineUpdatePayload(BaseModel):
    note: str | None = None


class MachineBatchUpdatePayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)
    note: str | None = None
    xs_to_auto: bool = False
    back_cond: bool = False

@router.get("/")
def get_inventory(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    status: str = Query("", description="按状态过滤"),
    model: str = Query("", description="按机型过滤"),
    order_id: str = Query("", description="按占用订单号过滤"),
):
    """分页获取库存数据。"""
    try:
        where_clauses = []
        params: Dict[str, Any] = {"skip": skip, "limit": limit}

        if str(status).strip():
            where_clauses.append("`状态` = :status")
            params["status"] = str(status).strip()
        if str(model).strip():
            where_clauses.append("`机型` = :model")
            params["model"] = str(model).strip()
        if str(order_id).strip():
            where_clauses.append("`占用订单号` = :order_id")
            params["order_id"] = str(order_id).strip()

        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        count_sql = f"SELECT COUNT(*) AS total FROM finished_goods_data{where_sql}"
        data_sql = (
            "SELECT * FROM finished_goods_data"
            f"{where_sql} "
            "ORDER BY `更新时间` DESC, `流水号` ASC LIMIT :limit OFFSET :skip"
        )

        with get_engine().connect() as conn:
            total_df = pd.read_sql(text(count_sql), conn, params=params)
            total = int(total_df.iloc[0]["total"]) if not total_df.empty else 0
            df = pd.read_sql(text(data_sql), conn, params=params)

        df = df.where(df.notnull(), None)
        return {
            "data": df.to_dict(orient="records"),
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
def update_inventory(
    data: List[Dict[str, Any]],
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    """
    Replace all inventory data with the provided list of dicts.
    Note: In actual production, you might want to use specific update/add endpoints instead of full replace.
    """
    import pandas as pd
    try:
        if data:
            if len(data) > MAX_INVENTORY_BULK_UPDATE_ROWS:
                raise HTTPException(
                    status_code=413,
                    detail=f"单次最多允许更新 {MAX_INVENTORY_BULK_UPDATE_ROWS} 条库存记录，请分批提交",
                )
            missing_sn = [idx for idx, item in enumerate(data) if not str(item.get("流水号", "")).strip()]
            if missing_sn:
                raise HTTPException(status_code=422, detail=f"第 {missing_sn[:10]} 条记录缺少必填字段: 流水号")
            candidate_models = [item.get("机型", "") for item in data if str(item.get("机型", "")).strip()]
            invalid_models = find_disabled_models(candidate_models)
            if invalid_models:
                sample = ", ".join(invalid_models[:10])
                suffix = "..." if len(invalid_models) > 10 else ""
                raise HTTPException(status_code=422, detail=f"机型不在字典中或未启用: {sample}{suffix}")
        df = pd.DataFrame(data)
        unknown_cols = [c for c in df.columns if c not in INVENTORY_COLS]
        if unknown_cols:
            raise HTTPException(status_code=422, detail=f"存在不支持字段: {unknown_cols}")
        cache.inventory.save_data(df)
        
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="全量更新",
            module="库存查询",
            biz_type="库存",
            content=f"全量覆盖更新库存数据，更新记录数：{len(data)}"
        )
        
        return {"message": "Inventory updated successfully"}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _notify_sandbox_background(sns: List[str]) -> None:
    for sn in sns:
        try:
            requests.post(f"{GO_SANDBOX_URL}/api/units/lookup/notify-update?sn={sn}", timeout=1)
        except Exception:
            pass


@router.put("/machine-edit/{serial_no}")
def machine_inline_update(
    serial_no: str, 
    payload: MachineInlineUpdatePayload,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        sn = str(serial_no).strip()
        if not sn:
            raise HTTPException(status_code=422, detail="流水号不能为空")
            
        changes = []
        note_val = None
        if payload.note is not None:
            note_val = str(payload.note).strip()
            changes.append(f"备注改为 {payload.note}")
            
        now_val = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        with get_engine().begin() as conn:
            # 校验流水号是否存在
            exists = conn.execute(
                text("SELECT COUNT(*) FROM finished_goods_data WHERE TRIM(`流水号`) = :sn"),
                {"sn": sn}
            ).scalar() or 0
            if exists == 0:
                raise HTTPException(status_code=404, detail="机台不存在")
                
            # 执行直接更新
            if payload.note is not None:
                conn.execute(
                    text("UPDATE finished_goods_data SET `合同备注` = :note, `更新时间` = :now WHERE TRIM(`流水号`) = :sn"),
                    {"note": note_val, "now": now_val, "sn": sn}
                )
            else:
                conn.execute(
                    text("UPDATE finished_goods_data SET `更新时间` = :now WHERE TRIM(`流水号`) = :sn"),
                    {"now": now_val, "sn": sn}
                )
                
        cache.inventory.cache_clear()
        
        try:
            _sync_machine_edit_to_units([sn])
        except Exception as e:
            logging.error(f"Failed to sync machine edit to units for SN {sn}: {e}")
        
        if changes:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="修改",
                module="机台档案",
                biz_type="机台",
                content=f"修改机台 {sn}；变更内容：{', '.join(changes)}"
            )
            
        # Notify Go Sandbox for real-time UI refresh in the background
        background_tasks.add_task(_notify_sandbox_background, [sn])
            
        return {"message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"机台更新失败: {e}")


@router.post("/machine-edit/batch-update")
def machine_batch_update(
    payload: MachineBatchUpdatePayload,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        sns = [str(x).strip() for x in (payload.serial_nos or []) if str(x).strip()]
        if not sns:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 台机台")

        changes = []
        note_parts = []
        if payload.note and str(payload.note).strip():
            note_parts.append(str(payload.note).strip())
        if payload.xs_to_auto:
            note_parts.append("XS改X手自一体")
        if payload.back_cond:
            note_parts.append("后导电")
            
        new_note = None
        if note_parts:
            new_note = "；".join(note_parts)
            changes.append(f"备注改为 {new_note}")
            
        now_val = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        with get_engine().begin() as conn:
            # 校验流水号是否存在并统计匹配行数
            match_count = conn.execute(
                text("SELECT COUNT(*) FROM finished_goods_data WHERE TRIM(`流水号`) IN :sns")
                .bindparams(bindparam("sns", expanding=True)),
                {"sns": sns}
            ).scalar() or 0
            if match_count == 0:
                raise HTTPException(status_code=404, detail="未找到对应机台")
                
            # 执行直接更新
            if new_note is not None:
                conn.execute(
                    text("UPDATE finished_goods_data SET `合同备注` = :note, `更新时间` = :now WHERE TRIM(`流水号`) IN :sns")
                    .bindparams(bindparam("sns", expanding=True)),
                    {"note": new_note, "now": now_val, "sns": sns}
                )
            else:
                conn.execute(
                    text("UPDATE finished_goods_data SET `更新时间` = :now WHERE TRIM(`流水号`) IN :sns")
                    .bindparams(bindparam("sns", expanding=True)),
                    {"now": now_val, "sns": sns}
                )
                
        cache.inventory.cache_clear()
        
        try:
            _sync_machine_edit_to_units(sns)
        except Exception as e:
            logging.error(f"Failed to sync machine batch edit to units: {e}")
        
        # Notify Go Sandbox in background
        if sns:
            background_tasks.add_task(_notify_sandbox_background, sns)
        
        if changes:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="批量修改",
                module="机台档案",
                biz_type="机台",
                content=f"批量修改 {match_count} 台机台；变更内容：{', '.join(changes)}"
            )
            
        return {"message": f"批量更新成功，共 {match_count} 台"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新失败: {e}")


@router.get("/layout/{layout_id}")
def get_layout(layout_id: str):
    try:
        return get_warehouse_layout(layout_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/layout/save")
def save_layout(
    payload: LayoutPayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        res = save_warehouse_layout(payload.layout_id, payload.layout_json)
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="修改",
            module="库位大屏",
            biz_type="库位大屏",
            content=f"修改库位大屏配置 ({payload.layout_id})"
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/layout/reset")
def reset_layout(
    payload: LayoutResetPayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        res = reset_warehouse_layout(payload.layout_id)
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="重置",
            module="库位大屏",
            biz_type="库位大屏",
            content=f"重置库位大屏配置 ({payload.layout_id})"
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inbound-to-slot")
def inbound_machine_to_slot(
    payload: InboundSlotPayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        operator = current_user.get("name") or current_user.get("username") or "System"
        result = cache.inventory.inbound_to_slot(
            payload.serial_no,
            payload.slot_code,
            is_transfer=bool(payload.is_transfer),
            operator=operator,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        
        action = "调拨机台" if payload.is_transfer else "机台入库"
        append_audit_log(
            user_id=current_user.get("username"),
            username=operator,
            action_type="调拨" if payload.is_transfer else "入库",
            module="入库作业",
            biz_type="机台",
            content=f"{action} 1 台机台；流水号：{payload.serial_no}，目标库位：{payload.slot_code}"
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import-staging")
def get_import_staging_rows(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
):
    try:
        with get_engine().connect() as conn:
            total_df = pd.read_sql(text("SELECT COUNT(*) AS total FROM plan_import"), conn)
            total = int(total_df.iloc[0]["total"]) if not total_df.empty else 0
            df = pd.read_sql(
                text("SELECT * FROM plan_import ORDER BY `流水号` DESC LIMIT :limit OFFSET :skip"),
                conn,
                params={"limit": limit, "skip": skip},
            )
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records"), "total": total, "skip": skip, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-staging/save")
def save_import_staging_rows(
    payload: ImportStagingSavePayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    import pandas as pd

    try:
        df = pd.DataFrame(payload.rows or [])
        if not df.empty and "机型" in df.columns:
            for model in df["机型"].astype(str).tolist():
                if model.strip():
                    _assert_model_enabled(model)
        save_import_staging(df)
        
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="保存",
            module="入库作业",
            biz_type="待入库数据",
            content=f"保存待入库清单，共 {len(df)} 条记录"
        )
        
        return {"message": "待入库清单保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


logger = logging.getLogger(__name__)


def _auto_revoke_sandbox_batches(batch_codes: list):
    """Revoke sandbox batches whose plan_import records were all deleted.
    Updates the shared MySQL database directly instead of calling Go HTTP API.
    """
    engine = get_engine()
    with engine.begin() as conn:
        for bc in batch_codes:
            result = conn.execute(
                text(
                    "UPDATE batches SET status = 'Predicted', batch_code = NULL "
                    "WHERE batch_code = :bc AND status = 'Confirmed'"
                ),
                {"bc": bc},
            )
            if result.rowcount and result.rowcount > 0:
                logger.info(
                    f"Auto-revoked {result.rowcount} sandbox batch(es) for batch_code={bc}"
                )


@router.post("/import-staging/delete")
def delete_import_staging_rows(
    payload: ImportStagingDeletePayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        serial_nos = [str(x).strip() for x in (payload.serial_nos or []) if str(x).strip()]
        if not serial_nos:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 条数据")
        result = delete_import_staging_by_serials(serial_nos)
        deleted = result["deleted"]
        orphaned_codes = result["orphaned_batch_codes"]

        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="删除",
            module="入库作业",
            biz_type="待入库数据",
            content=f"删除 {deleted} 条待入库数据"
        )

        # Auto-revoke sandbox batches whose plan_import records are all deleted
        if orphaned_codes:
            _auto_revoke_sandbox_batches(orphaned_codes)

        return {"message": f"已删除 {deleted} 条待入库数据", "deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.get("/shipping/pending")
def get_shipping_pending():
    try:
        df = cache.inventory.get_data()
        pending = df[df["状态"].astype(str) == "待发货"].copy()
        if pending.empty:
            return {"data": [], "total": 0}

        if "占用订单号" not in pending.columns:
            pending["占用订单号"] = ""
        pending["占用订单号"] = pending["占用订单号"].astype(str).str.strip()
        pending.loc[pending["占用订单号"].isin(["nan", "None", "NaT"]), "占用订单号"] = ""

        orders_df = get_orders()
        if not orders_df.empty:
            odf = orders_df[orders_df["status"].astype(str) != "deleted"].copy()
            odf["订单号"] = odf["订单号"].astype(str).str.strip()
            # 修改点：只要是被占用的订单号存在于 sales_orders 中即可，不限制订单状态必须为 ready
            # 因为发货复核主要是看机器实物的状态（是否为待发货）
            ready_order_ids = set(odf["订单号"].tolist())
            pending = pending[pending["占用订单号"].isin(ready_order_ids)].copy()
            if pending.empty:
                return {"data": [], "total": 0}
            date_map = odf.set_index("订单号")["发货时间"].to_dict()
            if "合同备注" not in pending.columns:
                pending["合同备注"] = ""
        else:
            return {"data": [], "total": 0}

        def _clean_shipping_note(value):
            if value is None:
                return ""
            text = str(value).strip()
            if not text:
                return ""
            lowered = text.lower()
            if lowered in {"none", "nan", "null"}:
                return ""
            if text == "合同导入" or text.startswith("合同导入:") or text.startswith("合同导入："):
                return ""
            if text.endswith(":None") or text.endswith("：None"):
                return ""
            text = re.sub(r'^合同\S+自动生成[；;]?\s*', '', text)
            if not text:
                return ""
            return text

        from crud.planning import get_factory_plan_v2
        plan_df = get_factory_plan_v2()
        model_note_map = {}
        if not plan_df.empty:
            plan_df["订单号"] = plan_df["订单号"].astype(str).str.strip()
            for _, row in plan_df.iterrows():
                order_no = str(row.get("订单号", "")).strip()
                model = str(row.get("机型", "")).strip()
                note = _clean_shipping_note(row.get("备注", ""))
                if order_no and model and note:
                    model_note_map.setdefault(order_no, {})[model] = note

        def _resolve_note(row):
            order_no = str(row.get("占用订单号", "")).strip()
            model = str(row.get("机型", "")).strip()
            existing = str(row.get("合同备注", "")).strip()
            if existing and existing.lower() not in {"none", "nan", "null"}:
                return _clean_shipping_note(existing)
            plan_note = model_note_map.get(order_no, {}).get(model, "")
            if plan_note:
                return plan_note
            return ""

        pending["合同备注"] = pending.apply(_resolve_note, axis=1)
        raw_dates = pending["占用订单号"].map(date_map)
        pending["发货时间"] = pd.to_datetime(raw_dates, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")

        pending = pending.where(pending.notnull(), None)
        return {"data": pending.to_dict(orient="records"), "total": len(pending)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取待发货数据失败: {e}")


@router.post("/shipping/confirm")
def confirm_shipping(
    payload: ShippingActionPayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        sns = [str(x).strip() for x in (payload.serial_nos or []) if str(x).strip()]
        if not sns:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 台机台")
        select_stmt = (
            text("SELECT * FROM finished_goods_data WHERE `流水号` IN :sns")
            .bindparams(bindparam("sns", expanding=True))
        )
        update_stmt = (
            text(
                "UPDATE finished_goods_data "
                "SET `状态`='已出库', `更新时间`=:now_text "
                "WHERE `流水号` IN :sns"
            )
            .bindparams(bindparam("sns", expanding=True))
        )

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
        with get_engine().begin() as conn:
            hit_rows = conn.execute(select_stmt, {"sns": sns}).mappings().all()
            if not hit_rows:
                raise HTTPException(status_code=422, detail="所选机台不存在")
            conn.execute(update_stmt, {"sns": sns, "now_text": now_text})
        enqueue_wechat_batch_summary_sync("shipping_confirm_inventory")

        hit = pd.DataFrame([dict(row) for row in hit_rows]).fillna("")
        impacted_order_ids = {
            str(x).strip()
            for x in hit.get("占用订单号", pd.Series(dtype=str)).tolist()
            if str(x).strip()
        }
        shipped_rows = hit.copy()
        shipped_rows["状态"] = "已出库"
        shipped_rows["更新时间"] = now_text

        if impacted_order_ids:
            orders_df = get_orders()
            changed = False
            shipped_counts: dict[str, int] = {}
            shipped_count_stmt = text(
                "SELECT COUNT(*) FROM finished_goods_data "
                "WHERE `状态`='已出库' AND TRIM(COALESCE(`占用订单号`, '')) = :order_id"
            )
            with get_engine().connect() as conn:
                for order_id in impacted_order_ids:
                    shipped_counts[order_id] = int(
                        conn.execute(shipped_count_stmt, {"order_id": order_id}).scalar() or 0
                    )
            for idx, row in orders_df.iterrows():
                order_id = str(row.get("订单号", "") or "").strip()
                if order_id not in impacted_order_ids:
                    continue
                need = 0
                raw = str(row.get("需求机型", "") or "")
                for token_raw in re.split(r"[;；/,，]", raw):
                    token = token_raw.strip()
                    if not token:
                        continue
                    m = re.search(r"(?:[x×:：]\s*)(\d+)\s*$", token, re.IGNORECASE)
                    if m:
                        try:
                            need += int(m.group(1))
                        except Exception:
                            pass
                if need <= 0:
                    try:
                        need = int(float(row.get("需求数量", 0) or 0))
                    except Exception:
                        need = 0
                shipped = shipped_counts.get(order_id, 0)
                if need > 0 and shipped >= need and str(row.get("status", "active") or "active") != "done":
                    orders_df.at[idx, "status"] = "done"
                    changed = True
            if changed:
                save_orders(orders_df)

        archive_shipped_data(shipped_rows)
        append_log("正式发货", sns, operator=current_operator)
        append_audit_log(
            module="发货复核",
            action_type="确认发货",
            biz_type="机台",
            content=f"确认发货 {len(sns)} 台机台；流水号：{', '.join(sns[:10])}",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        cloud_warning = ""
        cloud_synced = 0
        if impacted_order_ids:
            try:
                dealer_orders = sync_dealer_order_statuses_by_sales_orders(list(impacted_order_ids))
                for dealer_order in dealer_orders:
                    if dealer_order.get("status") == "completed":
                        enqueue_cloud_sync_event(
                            "dealer_order_completed",
                            str(dealer_order.get("order_no") or ""),
                            {
                                "order_no": str(dealer_order.get("order_no") or ""),
                                "contract_no": str(dealer_order.get("contract_no") or ""),
                                "operator": current_operator,
                                "v7_order_no": str(dealer_order.get("v7_order_no") or ""),
                            },
                        )
                        cloud_synced += 1
                enqueue_wechat_batch_summary_sync("shipping_confirm")
            except Exception as cloud_exc:
                cloud_warning = f"本地发货已完成，但回写小程序云端失败：{cloud_exc}"
        return {"message": f"发货完成，共 {len(sns)} 台", "warning": cloud_warning, "cloud_synced": cloud_synced}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"正式发货失败: {e}")


@router.post("/shipping/revert")
def revert_shipping(
    payload: ShippingActionPayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        sns = [str(x).strip() for x in (payload.serial_nos or []) if str(x).strip()]
        if not sns:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 台机台")
        revert_to_inbound(sns, reason="正式发货撤回", operator=current_operator)
        append_audit_log(
            module="发货复核",
            action_type="撤回发货",
            biz_type="机台",
            content=f"撤回发货 {len(sns)} 台机台；流水号：{', '.join(sns[:10])}",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": f"已撤回，共 {len(sns)} 台"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发货撤回失败: {e}")


def _safe_name(value: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", str(value or "")).strip()


def _ensure_sn_dir(serial_no: str) -> str:
    safe_sn = _safe_name(serial_no)
    if not safe_sn:
        raise HTTPException(status_code=422, detail="流水号不能为空")
    sn_dir = os.path.join(MACHINE_ARCHIVE_ABS_DIR, safe_sn)
    os.makedirs(sn_dir, exist_ok=True)
    return sn_dir


@router.get("/machine-archive/serials")
def machine_archive_serials():
    try:
        df = cache.inventory.get_data()
        sns = sorted(df["流水号"].astype(str).str.strip().replace({"nan": ""}).tolist(), reverse=True) if not df.empty else []
        sns = [x for x in sns if x]
        return {"data": sns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取流水号失败: {e}")


@router.get("/machine-archive/{serial_no}/files")
def machine_archive_files(serial_no: str):
    try:
        sn_dir = _ensure_sn_dir(serial_no)
        files = []
        if os.path.exists(sn_dir):
            for name in os.listdir(sn_dir):
                abs_path = os.path.join(sn_dir, name)
                if not os.path.isfile(abs_path):
                    continue
                ext = os.path.splitext(name)[1].lower()
                files.append({
                    "file_name": name,
                    "ext": ext,
                    "is_image": ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif"],
                    "size": os.path.getsize(abs_path),
                    "update_time": datetime.fromtimestamp(os.path.getmtime(abs_path)).strftime("%Y-%m-%d %H:%M:%S"),
                })
        files.sort(key=lambda x: x["update_time"], reverse=True)
        return {"data": files}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取档案文件失败: {e}")


@router.post("/machine-archive/{serial_no}/upload")
async def machine_archive_upload(
    serial_no: str, 
    label: str = Form(""), 
    files: List[UploadFile] = File(...),
    request: Request = None,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        if not files:
            raise HTTPException(status_code=422, detail="请至少上传 1 个文件")
        sn_dir = _ensure_sn_dir(serial_no)
        saved_names = []
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = _safe_name(label) or "档案"
        for idx, up in enumerate(files, start=1):
            ext = os.path.splitext(str(up.filename or ""))[1].lower() or ".jpg"
            if ext not in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif", ".pdf", ".doc", ".docx", ".txt"]:
                continue
            final_name = f"{safe_label}_{idx}_{ts}{ext}"
            save_path = os.path.join(sn_dir, final_name)
            await up.seek(0)
            async with aiofiles.open(save_path, "wb") as f:
                while True:
                    chunk = await up.read(1024 * 1024)
                    if not chunk:
                        break
                    await f.write(chunk)
            saved_names.append(final_name)
            await up.close()

        saved = len(saved_names)
        if saved <= 0:
            raise HTTPException(status_code=422, detail="没有可保存的有效文件")
            
        if request and current_user:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="上传",
                module="机台档案",
                biz_type="附件",
                content=f"上传机台档案 {saved} 个文件；流水号：{serial_no}"
            )
            
        return {"message": f"上传成功，共 {saved} 个文件", "saved_names": saved_names}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传档案失败: {e}")


@router.get("/machine-archive/{serial_no}/files/{file_name}/download")
def machine_archive_download(serial_no: str, file_name: str):
    try:
        sn_dir = _ensure_sn_dir(serial_no)
        safe_file = _safe_name(file_name)
        abs_path = os.path.join(sn_dir, safe_file)
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(path=abs_path, filename=safe_file)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")


@router.get("/machine-archive/{serial_no}/files/{file_name}/thumbnail")
def machine_archive_thumbnail(serial_no: str, file_name: str):
    """
    获取机台档案缩略图（带磁盘缓存优化）
    缓存路径: machine_archives/{serial_no}/.thumbs/{file_name}.thumb.jpg
    """
    try:
        sn_dir = _ensure_sn_dir(serial_no)
        safe_file = _safe_name(file_name)
        abs_path = os.path.join(sn_dir, safe_file)
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail="文件不存在")

        ext = os.path.splitext(safe_file)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]:
            return FileResponse(path=abs_path, filename=safe_file)

        # 缩略图缓存目录
        thumb_dir = os.path.join(sn_dir, ".thumbs")
        thumb_filename = f"{safe_file}.thumb.jpg"
        thumb_path = os.path.join(thumb_dir, thumb_filename)

        # 检查缓存：缓存存在且比原图新则直接返回
        if os.path.exists(thumb_path):
            try:
                orig_mtime = os.path.getmtime(abs_path)
                thumb_mtime = os.path.getmtime(thumb_path)
                if thumb_mtime >= orig_mtime:
                    logger.debug(f"Returning cached thumbnail: {thumb_path}")
                    return FileResponse(path=thumb_path, media_type="image/jpeg")
            except Exception:
                # 缓存检查失败，继续生成新缩略图
                pass

        # 动态生成缩略图
        with Image.open(abs_path) as img:
            # 如果原图已经很小，直接返回原图（不缓存）
            if img.width <= 400 and img.height <= 400:
                return FileResponse(path=abs_path, filename=safe_file)

            # 等比例缩小
            img.thumbnail((400, 400))

            # 确保缓存目录存在
            os.makedirs(thumb_dir, exist_ok=True)

            # 保存到缓存（统一转为 JPEG 压缩体积）
            img.convert('RGB').save(thumb_path, format="JPEG", quality=80)

            # 返回缓存文件
            return FileResponse(path=thumb_path, media_type="image/jpeg")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate thumbnail for {serial_no}/{file_name}")
        raise HTTPException(status_code=500, detail=f"获取缩略图失败: {e}")


@router.get("/machine-archive/{serial_no}/files/{file_name}/preview")
def machine_archive_preview(serial_no: str, file_name: str):
    try:
        sn_dir = _ensure_sn_dir(serial_no)
        safe_file = _safe_name(file_name)
        abs_path = os.path.join(sn_dir, safe_file)
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        ext = os.path.splitext(safe_file)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".gif": "image/gif", ".bmp": "image/bmp"
        }
        media_type = mime_types.get(ext, "image/jpeg")
        
        return FileResponse(path=abs_path, media_type=media_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {e}")


@router.delete("/machine-archive/{serial_no}/files/{file_name}")
def machine_archive_delete(
    serial_no: str, 
    file_name: str,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        sn_dir = _ensure_sn_dir(serial_no)
        safe_file = _safe_name(file_name)
        abs_path = os.path.join(sn_dir, safe_file)
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        os.remove(abs_path)
        
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="删除",
            module="机台档案",
            biz_type="附件",
            content=f"删除机台档案文件 {safe_file}；流水号：{serial_no}"
        )
        
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.post("/machine-archive/{serial_no}/files/batch-delete")
def machine_archive_batch_delete(
    serial_no: str, 
    payload: ArchiveBatchDeletePayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        names = [_safe_name(x) for x in (payload.file_names or []) if _safe_name(x)]
        if not names:
            raise HTTPException(status_code=422, detail="请先选择要删除的文件")
        sn_dir = _ensure_sn_dir(serial_no)
        deleted = 0
        missing = 0
        for name in names:
            abs_path = os.path.join(sn_dir, name)
            if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
                missing += 1
                continue
            os.remove(abs_path)
            deleted += 1
            
        if deleted > 0:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="批量删除",
                module="机台档案",
                biz_type="附件",
                content=f"批量删除机台档案 {deleted} 个文件；流水号：{serial_no}"
            )
            
        return {"message": f"批量删除完成，成功 {deleted}，不存在 {missing}", "deleted": deleted, "missing": missing}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量删除失败: {e}")
