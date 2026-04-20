from io import BytesIO
from typing import List, Dict, Any
from datetime import datetime
import asyncio
import pandas as pd
import os
import re
import tempfile
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from config import MACHINE_ARCHIVE_ABS_DIR
from core.file_manager import audit_log
from crud.audit_logs import append_audit_log
from crud.inventory import (
    INVENTORY_COLS,
    append_import_staging,
    delete_import_staging_by_serials,
    get_data,
    get_import_staging,
    get_warehouse_layout,
    inbound_to_slot,
    reset_warehouse_layout,
    save_data,
    save_import_staging,
    save_warehouse_layout,
    archive_shipped_data,
)
from crud.logs import append_log
from crud.model_dictionary import find_disabled_models, is_model_enabled
from crud.orders import get_orders, revert_to_inbound
from api.routes.auth import get_current_operator_name, get_current_user_context, get_current_user_token
from database import get_engine
from utils.parsers import (
    build_import_payload,
    diff_tracking_vs_inventory,
    execute_import_transaction_payload,
    generate_auto_inbound,
    parse_tracking_xls,
)

router = APIRouter(dependencies=[Depends(get_current_user_token)])
MAX_INVENTORY_BULK_UPDATE_ROWS = 20000


def _assert_model_enabled(model_name: str) -> None:
    model = str(model_name or "").replace("(加高)", "").strip()
    if not model:
        raise HTTPException(status_code=422, detail="机型不能为空")
    if not is_model_enabled(model):
        raise HTTPException(status_code=422, detail=f"机型不在字典中或未启用: {model}")


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


class ImportConfirmPayload(BaseModel):
    selected_track_nos: List[str] = Field(default_factory=list)
    expected_inbound_date: str = ""


class ImportStagingDeletePayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)


class AutoGeneratePayload(BaseModel):
    batch: str
    model: str
    qty: int = Field(gt=0)
    expected_inbound_date: str
    machine_note: str = ""


class ShippingActionPayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)


class ArchiveBatchDeletePayload(BaseModel):
    file_names: List[str] = Field(default_factory=list)


class MachineInlineUpdatePayload(BaseModel):
    model: str | None = None
    note: str | None = None


class MachineBatchUpdatePayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)
    model: str | None = None
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
            "ORDER BY `更新时间` DESC LIMIT :limit OFFSET :skip"
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
        save_data(df)
        
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


@router.put("/machine-edit/{serial_no}")
def machine_inline_update(
    serial_no: str, 
    payload: MachineInlineUpdatePayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        sn = str(serial_no).strip()
        if not sn:
            raise HTTPException(status_code=422, detail="流水号不能为空")
        df = get_data()
        mask = df["流水号"].astype(str).str.strip() == sn
        if not mask.any():
            raise HTTPException(status_code=404, detail="机台不存在")
            
        changes = []
        if payload.model is not None:
            model = str(payload.model).strip()
            _assert_model_enabled(model)
            df.loc[mask, "机型"] = model
            changes.append(f"机型改为 {model}")
        if payload.note is not None:
            df.loc[mask, "机台备注/配置"] = str(payload.note).strip()
            changes.append(f"备注改为 {payload.note}")
            
        df.loc[mask, "更新时间"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_data(df)
        
        if changes:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="修改",
                module="机台档案",
                biz_type="机台",
                content=f"修改机台 {sn}；变更内容：{', '.join(changes)}"
            )
            
        return {"message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"机台更新失败: {e}")


@router.post("/machine-edit/batch-update")
def machine_batch_update(
    payload: MachineBatchUpdatePayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        sns = [str(x).strip() for x in (payload.serial_nos or []) if str(x).strip()]
        if not sns:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 台机台")
        df = get_data()
        mask = df["流水号"].astype(str).isin(sns)
        if not mask.any():
            raise HTTPException(status_code=404, detail="未找到对应机台")

        changes = []
        if payload.model is not None and str(payload.model).strip():
            _assert_model_enabled(str(payload.model).strip())
            df.loc[mask, "机型"] = str(payload.model).strip()
            changes.append(f"机型改为 {payload.model}")

        note_parts = []
        if payload.note and str(payload.note).strip():
            note_parts.append(str(payload.note).strip())
        if payload.xs_to_auto:
            note_parts.append("XS改X手自一体")
        if payload.back_cond:
            note_parts.append("后导电")
        if note_parts:
            new_note = "；".join(note_parts)
            df.loc[mask, "机台备注/配置"] = new_note
            changes.append(f"备注改为 {new_note}")
            
        df.loc[mask, "更新时间"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_data(df)
        
        if changes:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="批量修改",
                module="机台档案",
                biz_type="机台",
                content=f"批量修改 {int(mask.sum())} 台机台；变更内容：{', '.join(changes)}"
            )
            
        return {"message": f"批量更新成功，共 {int(mask.sum())} 台"}
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
        result = inbound_to_slot(payload.serial_no, payload.slot_code, is_transfer=bool(payload.is_transfer))
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        
        action = "调拨机台" if payload.is_transfer else "机台入库"
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
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


@router.post("/import-staging/upload")
async def upload_tracking_sheet(
    file: UploadFile = File(...),
    request: Request = None,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="请选择跟踪单文件")
        lower_name = file.filename.lower()
        if not (lower_name.endswith(".xls") or lower_name.endswith(".xlsx")):
            raise HTTPException(status_code=400, detail="仅支持 .xls / .xlsx 文件")

        suffix = os.path.splitext(file.filename)[1].lower() or ".xlsx"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            async with aiofiles.open(tmp_path, "wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    await out.write(chunk)
        finally:
            await file.close()

        class _DiskUpload:
            def __init__(self, name: str, path: str):
                self.name = name
                self._path = path

            def read(self):
                with open(self._path, "rb") as f:
                    return f.read()

        code, msg, parsed_df = await asyncio.to_thread(parse_tracking_xls, _DiskUpload(file.filename, tmp_path))
        if code != 1:
            raise HTTPException(status_code=422, detail=msg)

        diff_df = await asyncio.to_thread(diff_tracking_vs_inventory, parsed_df)
        if diff_df.empty:
            return {"message": "所有解析到的流水号均已在库存中，无需导入。", "appended": 0}
        for model in diff_df.get("机型", pd.Series(dtype=str)).astype(str).tolist():
            if model.strip():
                _assert_model_enabled(model)

        appended = await asyncio.to_thread(append_import_staging, diff_df)
        
        if request and current_user:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="上传",
                module="入库作业",
                biz_type="待入库数据",
                content=f"解析文件 {file.filename}，追加 {appended} 条待入库数据"
            )
            
        return {"message": f"解析成功！已追加 {appended} 条记录到待入库清单。", "appended": appended}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传解析失败: {e}")
    finally:
        try:
            if "tmp_path" in locals() and tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


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
        deleted = delete_import_staging_by_serials(serial_nos)
        
        append_audit_log(
            user_id=current_user.get("username"),
            username=current_user.get("name") or current_user.get("username") or "System",
            action_type="删除",
            module="入库作业",
            biz_type="待入库数据",
            content=f"删除 {deleted} 条待入库数据"
        )
        
        return {"message": f"已删除 {deleted} 条待入库数据", "deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.post("/import-staging/import-confirm")
def import_confirm(
    payload: ImportConfirmPayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    import pandas as pd

    try:
        if not payload.selected_track_nos:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 条数据")

        plan_df = get_import_staging().copy()
        if plan_df.empty:
            raise HTTPException(status_code=422, detail="待入库清单为空")
        plan_df["流水号"] = plan_df["流水号"].astype(str).str.strip()
        selected = [str(x).strip() for x in payload.selected_track_nos if str(x).strip()]
        selected_rows = plan_df[plan_df["流水号"].isin(selected)].copy()
        if selected_rows.empty:
            raise HTTPException(status_code=422, detail="所选记录已不存在，请刷新后重试")

        payload_data, err = build_import_payload(selected_rows, payload.expected_inbound_date)
        if err:
            raise HTTPException(status_code=422, detail=err)

        result = execute_import_transaction_payload(payload_data, retry_times=1)

        success_items = result.get("success", [])
        success_count = len(success_items)
        if success_count > 0:
            selected_row_map = {}
            for _, row in selected_rows.iterrows():
                serial_no = str(row.get("流水号", "")).strip()
                if serial_no:
                    selected_row_map[serial_no] = row

            for item in success_items:
                serial_no = str(item.get("trackNo", "")).strip()
                row = selected_row_map.get(serial_no)
                model_name = str((row.get("机型", "") if row is not None else "") or "").strip()
                batch_no = str((row.get("批次号", "") if row is not None else "") or "").strip()
                expected_date = str((row.get("预计入库时间", "") if row is not None else "") or "").strip()
                if not expected_date:
                    expected_date = str(payload.expected_inbound_date or "").strip()

                content_parts = [f"开始生产；流水号：{serial_no}"]
                if model_name:
                    content_parts.append(f"机型：{model_name}")
                if batch_no:
                    content_parts.append(f"批次号：{batch_no}")
                if expected_date:
                    content_parts.append(f"预计入库日期：{expected_date}")

                append_audit_log(
                    user_id=current_user.get("username"),
                    username=current_user.get("name") or current_user.get("username") or "System",
                    action_type="开始生产",
                    module="入库作业",
                    biz_type="待入库数据",
                    content="；".join(content_parts),
                )
            
        return {
            "success": result.get("success", []),
            "failed": result.get("failed", []),
            "success_count": success_count,
            "failed_count": len(result.get("failed", [])),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")


@router.post("/import-staging/auto-generate")
def auto_generate_import_rows(
    payload: AutoGeneratePayload,
    request: Request,
    current_user: dict = Depends(get_current_user_context)
):
    try:
        _assert_model_enabled(payload.model)
        code, msg = generate_auto_inbound(
            payload.batch,
            payload.model,
            int(payload.qty),
            payload.expected_inbound_date,
            payload.machine_note,
        )
        if code == 1:
            append_audit_log(
                user_id=current_user.get("username"),
                username=current_user.get("name") or current_user.get("username") or "System",
                action_type="自动生成",
                module="入库作业",
                biz_type="待入库数据",
                content=f"自动生成待入库数据 {payload.qty} 台；批次号：{payload.batch}，机型：{payload.model}"
            )
            return {"message": msg}
        raise HTTPException(status_code=422, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自动生成失败: {e}")


@router.get("/shipping/pending")
def get_shipping_pending():
    try:
        df = get_data()
        pending = df[df["状态"].astype(str) == "待发货"].copy()
        if pending.empty:
            return {"data": [], "total": 0}

        if "占用订单号" not in pending.columns:
            pending["占用订单号"] = ""
        pending["占用订单号"] = pending["占用订单号"].astype(str).str.strip()
        pending.loc[pending["占用订单号"].isin(["nan", "None", "NaT"]), "占用订单号"] = ""

        orders_df = get_orders()
        if not orders_df.empty:
            odf = orders_df.copy()
            odf["订单号"] = odf["订单号"].astype(str).str.strip()
            note_map = odf.set_index("订单号")["备注"].to_dict()
            date_map = odf.set_index("订单号")["发货时间"].to_dict()
            if "订单备注" not in pending.columns:
                pending["订单备注"] = ""
            mapped_notes = pending["占用订单号"].map(note_map)
            pending["订单备注"] = mapped_notes.fillna(pending["订单备注"])
            raw_dates = pending["占用订单号"].map(date_map)
            pending["发货时间"] = pd.to_datetime(raw_dates, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        else:
            if "发货时间" not in pending.columns:
                pending["发货时间"] = ""

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
        df = get_data()
        hit = df[df["流水号"].astype(str).isin(sns)]
        if hit.empty:
            raise HTTPException(status_code=422, detail="所选机台不存在")

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
        mask = df["流水号"].astype(str).isin(sns)
        df.loc[mask, "状态"] = "已出库"
        df.loc[mask, "更新时间"] = now_text
        save_data(df)
        archive_shipped_data(df[df["流水号"].astype(str).isin(sns)])
        append_log("正式发货", sns, operator=current_operator)
        append_audit_log(
            module="发货复核",
            action_type="确认发货",
            biz_type="机台",
            content=f"确认发货 {len(sns)} 台机台；流水号：{', '.join(sns[:10])}",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": f"发货完成，共 {len(sns)} 台"}
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
        df = get_data()
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
        saved = 0
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
            saved += 1
            await up.close()
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
            
        return {"message": f"上传成功，共 {saved} 个文件"}
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


@router.get("/machine-archive/{serial_no}/files/{file_name}/preview")
def machine_archive_preview(serial_no: str, file_name: str):
    try:
        sn_dir = _ensure_sn_dir(serial_no)
        safe_file = _safe_name(file_name)
        abs_path = os.path.join(sn_dir, safe_file)
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(path=abs_path)
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
