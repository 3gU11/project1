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
from crud.audit_logs import append_audit_log, append_operation_logs
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
from utils.model_compatibility import normalize_model_family, production_group_for_family
from crud.logs import append_log
from crud.model_dictionary import find_disabled_models, get_model_dictionary, is_model_enabled
from crud.orders import get_orders, revert_to_inbound, save_orders
from api.routes.auth import get_current_operator_name, get_current_user_context, get_current_user_token
from api.websockets.manager import manager
from database import get_engine


router = APIRouter(dependencies=[Depends(get_current_user_token)])
MAX_INVENTORY_BULK_UPDATE_ROWS = 20000
def _normalize_model_for_edit_rule(model_name: object) -> str:
    return str(model_name or "").replace("(加高)", "").replace("（加高）", "").strip()


def _normalize_model_family_for_edit_rule(family: object) -> str:
    return normalize_model_family(family)


def _model_lookup_keys(model_name: object) -> set[str]:
    clean = _normalize_model_for_edit_rule(model_name)
    if not clean:
        return set()
    upper = clean.upper()
    return {
        clean,
        upper,
        re.sub(r"\s+", "", upper),
        upper.replace("-", ""),
    }


def _load_model_family_lookup_for_edit_rule() -> dict[str, str]:
    lookup: dict[str, str] = {}
    try:
        rows = get_model_dictionary()
    except Exception as e:
        logging.warning("load model dictionary for machine edit rule failed: %s", e)
        return lookup
    for row in rows or []:
        family = _normalize_model_family_for_edit_rule(row.get("model_family"))
        for key in _model_lookup_keys(row.get("model_name")):
            lookup.setdefault(key, family)
    return lookup


def _fallback_model_family_for_edit_rule(model_name: object) -> str:
    value = _normalize_model_for_edit_rule(model_name).upper()
    if not value:
        return ""
    if value in {"中大型XS", "大机XS"}:
        return "中大型XS"
    if value in {"中大型AUTO", "大机AUTO"}:
        return "中大型AUTO"
    is_large = any(token in value for token in ("7055", "8055", "8060"))
    if not is_large:
        return ""
    if "AUTO" in value:
        return "中大型AUTO"
    if "XS" in value:
        return "中大型XS"
    return ""


def _model_family_for_edit_rule(model_name: object, family_lookup: dict[str, str] | None = None) -> str:
    family_lookup = family_lookup or {}
    for key in _model_lookup_keys(model_name):
        family = _normalize_model_family_for_edit_rule(family_lookup.get(key))
        if family:
            return family
    return _fallback_model_family_for_edit_rule(model_name)


def _is_bound_machine_row(row: dict[str, Any]) -> bool:
    return bool(str(row.get("占用订单号") or "").strip() or str(row.get("合同号") or "").strip())


def _format_machine_row_brief(row: dict[str, Any]) -> str:
    sn = str(row.get("流水号") or "").strip() or "-"
    model = str(row.get("机型") or "").strip() or "-"
    return f"{sn}({model})"


def _validate_compatible_model_change(
    machine_rows: list[dict[str, Any]],
    target_model: str,
    *,
    bound_change_confirmed: bool = False,
) -> None:
    family_lookup = _load_model_family_lookup_for_edit_rule()
    target_family = _model_family_for_edit_rule(target_model, family_lookup)
    target_group = production_group_for_family(target_family)
    if not target_family or not target_group:
        raise HTTPException(status_code=422, detail=f"目标机型未配置族类，无法改型: {target_model}")

    invalid_rows = [
        row
        for row in machine_rows
        if production_group_for_family(_model_family_for_edit_rule(row.get("机型"), family_lookup)) != target_group
    ]
    if invalid_rows:
        preview = "、".join(_format_machine_row_brief(row) for row in invalid_rows[:8])
        suffix = "等" if len(invalid_rows) > 8 else ""
        target_group_label = "中大型" if target_group == "LARGE" else target_family
        raise HTTPException(
            status_code=422,
            detail=f"仅允许同生产组改型；目标生产组为 {target_group_label}，请先剔除不兼容机台：{preview}{suffix}",
        )

    bound_rows = [row for row in machine_rows if _is_bound_machine_row(row)]
    if bound_rows:
        preview = "、".join(_format_machine_row_brief(row) for row in bound_rows[:8])
        suffix = "等" if len(bound_rows) > 8 else ""
        raise HTTPException(
            status_code=409,
            detail=f"已绑定合同或占用订单的机台请到合同管理修改机型：{preview}{suffix}",
        )


def _assert_model_enabled(model_name: str) -> None:
    model = _normalize_model_for_edit_rule(model_name)
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
                  ON TRIM(fg.`流水号`) COLLATE utf8mb4_general_ci =
                     COALESCE(
                         NULLIF(TRIM(u.serial_no), ''),
                         NULLIF(TRIM(u.forecast_serial_no), '')
                     ) COLLATE utf8mb4_general_ci
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


def _machine_edit_list_base_sql() -> str:
    return """
        SELECT
            TRIM(CONVERT(COALESCE(fg.`批次号`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `批次号`,
            TRIM(CONVERT(COALESCE(fg.`流水号`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `流水号`,
            TRIM(CONVERT(COALESCE(fg.`机型`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `机型`,
            TRIM(CONVERT(COALESCE(fg.`状态`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `状态`,
            TRIM(CONVERT(COALESCE(fg.`Location_Code`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `Location_Code`,
            TRIM(CONVERT(COALESCE(fg.`占用订单号`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `占用订单号`,
            TRIM(CONVERT(COALESCE(fg.`合同号`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `合同号`,
            TRIM(CONVERT(COALESCE(fg.`客户`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `客户`,
            TRIM(CONVERT(COALESCE(fg.`代理商`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `代理商`,
            TRIM(CONVERT(COALESCE(fg.`合同备注`, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `合同备注`,
            TRIM(CONVERT(COALESCE(CAST(fg.`更新时间` AS CHAR), '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `更新时间`
        FROM finished_goods_data fg
        WHERE TRIM(COALESCE(fg.`流水号`, '')) <> ''
          AND TRIM(COALESCE(fg.`状态`, '')) <> '报废'

        UNION ALL

        SELECT
            TRIM(CONVERT(COALESCE(b.batch_code, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `批次号`,
            TRIM(CONVERT(COALESCE(NULLIF(u.serial_no, ''), NULLIF(u.forecast_serial_no, '')) USING utf8mb4)) COLLATE utf8mb4_general_ci AS `流水号`,
            TRIM(CONVERT(COALESCE(u.model_type, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `机型`,
            '已确认' COLLATE utf8mb4_general_ci AS `状态`,
            '' COLLATE utf8mb4_general_ci AS `Location_Code`,
            TRIM(CONVERT(COALESCE(u.sales_id, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `占用订单号`,
            TRIM(CONVERT(COALESCE(u.contract_no, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `合同号`,
            TRIM(CONVERT(COALESCE(u.customer, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `客户`,
            TRIM(CONVERT(COALESCE(u.dealer_name, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `代理商`,
            TRIM(CONVERT(COALESCE(u.order_remark, '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `合同备注`,
            TRIM(CONVERT(COALESCE(DATE_FORMAT(COALESCE(u.updated_at, b.updated_at, u.created_at), '%Y-%m-%d %H:%i'), '') USING utf8mb4)) COLLATE utf8mb4_general_ci AS `更新时间`
        FROM units u
        JOIN batches b ON b.batch_id = u.batch_id
        LEFT JOIN finished_goods_data fg
          ON TRIM(fg.`流水号`) COLLATE utf8mb4_general_ci =
             COALESCE(
                 NULLIF(TRIM(u.serial_no), ''),
                 NULLIF(TRIM(u.forecast_serial_no), '')
             ) COLLATE utf8mb4_general_ci
        WHERE b.status = 'Confirmed'
          AND COALESCE(TRIM(COALESCE(NULLIF(u.serial_no, ''), NULLIF(u.forecast_serial_no, ''))), '') <> ''
          AND fg.`流水号` IS NULL
    """


def _load_machine_edit_rows_by_serials(conn, serial_nos: list[str]) -> list[dict[str, Any]]:
    sns = [str(x).strip() for x in serial_nos if str(x).strip()]
    if not sns:
        return []

    fg_rows = conn.execute(
        text(
            """
            SELECT
                TRIM(`流水号`) AS `流水号`,
                TRIM(COALESCE(`机型`, '')) AS `机型`,
                TRIM(COALESCE(`占用订单号`, '')) AS `占用订单号`,
                TRIM(COALESCE(`合同号`, '')) AS `合同号`,
                TRIM(COALESCE(`合同备注`, '')) AS `合同备注`,
                'finished_goods' AS `_source`,
                NULL AS `_unit_id`
            FROM finished_goods_data
            WHERE TRIM(`流水号`) IN :sns
            """
        ).bindparams(bindparam("sns", expanding=True)),
        {"sns": sns},
    ).mappings().all()

    row_by_sn = {
        str(row.get("流水号") or "").strip(): dict(row)
        for row in fg_rows
        if str(row.get("流水号") or "").strip()
    }
    pending_sns = [sn for sn in sns if sn not in row_by_sn]
    if not pending_sns:
        return [row_by_sn[sn] for sn in sns if sn in row_by_sn]

    unit_rows = conn.execute(
        text(
            """
            SELECT
                TRIM(COALESCE(NULLIF(u.serial_no, ''), NULLIF(u.forecast_serial_no, ''))) AS `流水号`,
                TRIM(COALESCE(u.model_type, '')) AS `机型`,
                TRIM(COALESCE(u.sales_id, '')) AS `占用订单号`,
                TRIM(COALESCE(u.contract_no, '')) AS `合同号`,
                TRIM(COALESCE(u.order_remark, '')) AS `合同备注`,
                'confirmed_unit' AS `_source`,
                u.unit_id AS `_unit_id`
            FROM units u
            JOIN batches b ON b.batch_id = u.batch_id
            LEFT JOIN finished_goods_data fg
              ON TRIM(fg.`流水号`) COLLATE utf8mb4_general_ci =
                 COALESCE(
                     NULLIF(TRIM(u.serial_no), ''),
                     NULLIF(TRIM(u.forecast_serial_no), '')
                 ) COLLATE utf8mb4_general_ci
            WHERE b.status = 'Confirmed'
              AND fg.`流水号` IS NULL
              AND TRIM(COALESCE(NULLIF(u.serial_no, ''), NULLIF(u.forecast_serial_no, ''))) IN :sns
            """
        ).bindparams(bindparam("sns", expanding=True)),
        {"sns": pending_sns},
    ).mappings().all()

    for row in unit_rows:
        sn = str(row.get("流水号") or "").strip()
        if sn and sn not in row_by_sn:
            row_by_sn[sn] = dict(row)
    return [row_by_sn[sn] for sn in sns if sn in row_by_sn]


def _sync_machine_edit_to_plan_import(
    conn,
    serial_nos: list[str],
    *,
    note: str | None = None,
    model_type: str | None = None,
) -> int:
    sns = [str(x).strip() for x in serial_nos if str(x).strip()]
    if not sns:
        return 0

    set_clauses = []
    params: Dict[str, Any] = {"sns": sns}
    if note is not None:
        set_clauses.append("`合同备注` = :note")
        params["note"] = note
    if model_type is not None:
        set_clauses.append("`机型` = :model_type")
        params["model_type"] = model_type
    if not set_clauses:
        return 0

    result = conn.execute(
        text(f"UPDATE plan_import SET {', '.join(set_clauses)} WHERE TRIM(`流水号`) IN :sns")
        .bindparams(bindparam("sns", expanding=True)),
        params,
    )
    return int(result.rowcount or 0)


def _apply_machine_edit_updates(
    conn,
    machine_rows: list[dict[str, Any]],
    *,
    note: str | None = None,
    model_type: str | None = None,
    now_val: str,
) -> None:
    fg_serials = [
        str(row.get("流水号") or "").strip()
        for row in machine_rows
        if str(row.get("_source") or "") == "finished_goods" and str(row.get("流水号") or "").strip()
    ]
    if fg_serials:
        set_clauses = ["`更新时间` = :now"]
        params: Dict[str, Any] = {"now": now_val, "sns": fg_serials}
        if note is not None:
            set_clauses.append("`合同备注` = :note")
            params["note"] = note
        if model_type is not None:
            set_clauses.append("`机型` = :model_type")
            params["model_type"] = model_type
        conn.execute(
            text(f"UPDATE finished_goods_data SET {', '.join(set_clauses)} WHERE TRIM(`流水号`) IN :sns")
            .bindparams(bindparam("sns", expanding=True)),
            params,
        )

    confirmed_rows = [
        row
        for row in machine_rows
        if str(row.get("_source") or "") == "confirmed_unit" and str(row.get("_unit_id") or "").strip()
    ]
    if confirmed_rows:
        unit_ids = [str(row.get("_unit_id") or "").strip() for row in confirmed_rows if str(row.get("_unit_id") or "").strip()]
        set_clauses = ["updated_at = NOW()"]
        params = {"unit_ids": unit_ids}
        if note is not None:
            set_clauses.append("order_remark = :note")
            params["note"] = note
        if model_type is not None:
            set_clauses.append("model_type = :model_type")
            params["model_type"] = model_type
        conn.execute(
            text(f"UPDATE units SET {', '.join(set_clauses)} WHERE unit_id IN :unit_ids")
            .bindparams(bindparam("unit_ids", expanding=True)),
            params,
        )
        _sync_machine_edit_to_plan_import(
            conn,
            [str(row.get("流水号") or "").strip() for row in confirmed_rows],
            note=note,
            model_type=model_type,
        )


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


class ShippingReturnPayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)
    action: str = Field(default="reallocate")
    reason: str = ""


class ArchiveBatchDeletePayload(BaseModel):
    file_names: List[str] = Field(default_factory=list)


class MachineInlineUpdatePayload(BaseModel):
    note: str | None = None
    model_type: str | None = None
    confirm_bound_change: bool = False


class MachineBatchUpdatePayload(BaseModel):
    serial_nos: List[str] = Field(default_factory=list)
    note: str | None = None
    model_type: str | None = None
    xs_to_auto: bool = False
    back_cond: bool = False
    confirm_bound_change: bool = False

@router.get("/")
def get_inventory(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    status: str = Query("", description="按状态过滤"),
    model: str = Query("", description="按机型过滤"),
    order_id: str = Query("", description="按占用订单号过滤"),
    include_scrap: bool = Query(False, description="是否包含报废机台"),
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
        if not include_scrap:
            where_clauses.append("TRIM(COALESCE(`状态`, '')) <> '报废'")

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


@router.get("/machine-edit/list")
def get_machine_edit_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
):
    """分页获取机台编辑列表，包含已入库机台与已确认未入库机台。"""
    try:
        base_sql = _machine_edit_list_base_sql()
        count_sql = f"SELECT COUNT(*) AS total FROM ({base_sql}) t"
        data_sql = (
            f"SELECT * FROM ({base_sql}) t "
            "ORDER BY `更新时间` DESC, `流水号` ASC LIMIT :limit OFFSET :skip"
        )

        with get_engine().connect() as conn:
            total_df = pd.read_sql(text(count_sql), conn)
            total = int(total_df.iloc[0]["total"]) if not total_df.empty else 0
            df = pd.read_sql(text(data_sql), conn, params={"limit": limit, "skip": skip})

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


def _ensure_shipping_return_history_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS shipping_return_history (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `流水号` VARCHAR(100) NOT NULL,
            `原订单号` VARCHAR(100) DEFAULT '',
            `机型` VARCHAR(100) DEFAULT '',
            `客户` VARCHAR(200) DEFAULT '',
            `代理商` VARCHAR(200) DEFAULT '',
            `合同号` VARCHAR(100) DEFAULT '',
            `退回类型` VARCHAR(32) DEFAULT '',
            `退回原因` TEXT,
            `退回前状态` VARCHAR(50) DEFAULT '',
            `退回后状态` VARCHAR(50) DEFAULT '',
            `操作人` VARCHAR(100) DEFAULT '',
            `操作时间` DATETIME NULL,
            PRIMARY KEY (`id`),
            INDEX `idx_shipping_return_sn` (`流水号`),
            INDEX `idx_shipping_return_order` (`原订单号`),
            INDEX `idx_shipping_return_time` (`操作时间`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))


def _parse_order_demand_counts_for_shipping(row: pd.Series) -> dict[str, int]:
    raw = str(row.get("需求机型", "") or "")
    counts: dict[str, int] = {}
    for token_raw in re.split(r"[;；/,，]", raw):
        token = token_raw.strip()
        if not token:
            continue
        qty_match = re.search(r"(?:[x×:：]\s*)(\d+)\s*$", token, flags=re.IGNORECASE)
        qty = int(qty_match.group(1)) if qty_match else 0
        model = re.sub(r"(?:[x×:：]\s*)\d+\s*$", "", token, flags=re.IGNORECASE)
        model = model.replace("(加高)", "").replace("（加高）", "").strip()
        if model and qty > 0:
            counts[model] = counts.get(model, 0) + qty
    if counts:
        return counts
    fallback_model = raw.replace("(加高)", "").replace("（加高）", "").strip()
    try:
        fallback_qty = int(float(row.get("需求数量", 0) or 0))
    except Exception:
        fallback_qty = 0
    if fallback_model and fallback_qty > 0:
        return {fallback_model: fallback_qty}
    return {}


def _normalize_shipping_model(value: object) -> str:
    return str(value or "").replace("(加高)", "").replace("（加高）", "").strip()


def _order_rows_satisfy_shipping_need(order_row: pd.Series, machine_rows: pd.DataFrame) -> bool:
    demand_counts = _parse_order_demand_counts_for_shipping(order_row)
    if not demand_counts or machine_rows.empty:
        return False
    allocated_counts: dict[str, int] = {}
    for _, machine_row in machine_rows.iterrows():
        model = _normalize_shipping_model(machine_row.get("机型", ""))
        if model:
            allocated_counts[model] = allocated_counts.get(model, 0) + 1
    for model, need in demand_counts.items():
        if allocated_counts.get(_normalize_shipping_model(model), 0) < need:
            return False
    return True


def _recompute_order_status_after_shipping_return(order_id: str) -> str:
    order_id = str(order_id or "").strip()
    if not order_id:
        return ""
    orders_df = get_orders()
    hit = orders_df[orders_df["订单号"].astype(str).str.strip() == order_id]
    if hit.empty:
        return ""
    idx = hit.index[0]
    current_status = str(orders_df.at[idx, "status"] or "active").strip()
    if current_status == "deleted":
        return current_status

    with get_engine().connect() as conn:
        inv_df = pd.read_sql(
            text(
                "SELECT `机型`, `状态`, `占用订单号`, `流水号` "
                "FROM finished_goods_data "
                "WHERE TRIM(COALESCE(`占用订单号`, '')) = :order_id"
            ),
            conn,
            params={"order_id": order_id},
        )
    if inv_df.empty:
        new_status = "active"
    else:
        for col in ["机型", "状态", "占用订单号", "流水号"]:
            if col not in inv_df.columns:
                inv_df[col] = ""
        inv_df["状态"] = inv_df["状态"].astype(str).str.strip()
        shipped_rows = inv_df[inv_df["状态"] == "已出库"].copy()
        pending_rows = inv_df[inv_df["状态"] == "待发货"].copy()
        order_row = orders_df.loc[idx]
        if _order_rows_satisfy_shipping_need(order_row, shipped_rows):
            new_status = "done"
        elif _order_rows_satisfy_shipping_need(order_row, pending_rows):
            new_status = "ready"
        else:
            new_status = "active"

    if current_status != new_status:
        orders_df.at[idx, "status"] = new_status
        save_orders(orders_df)
    return new_status


def _clear_units_for_returned_serials(conn, serial_nos: list[str]) -> int:
    sns = [str(sn or "").strip() for sn in serial_nos if str(sn or "").strip()]
    if not sns:
        return 0
    exists = conn.execute(text("SHOW TABLES LIKE 'units'")).fetchone()
    if not exists:
        return 0
    cols = {
        str(row[0])
        for row in conn.execute(text("SHOW COLUMNS FROM units")).fetchall()
    }
    set_parts = []
    for col, expr in [
        ("contract_no", "contract_no = NULL"),
        ("customer", "customer = NULL"),
        ("dealer_name", "dealer_name = NULL"),
        ("dealer_id", "dealer_id = NULL"),
        ("due_date", "due_date = NULL"),
        ("sales_id", "sales_id = NULL"),
        ("order_remark", "order_remark = NULL"),
        ("is_locked", "is_locked = 0"),
        ("locked_by", "locked_by = NULL"),
        ("locked_at", "locked_at = NULL"),
        ("is_contract_pinned", "is_contract_pinned = 0"),
        ("updated_at", "updated_at = NOW()"),
    ]:
        if col in cols:
            set_parts.append(expr)
    if not set_parts:
        return 0
    serial_col = "serial_no" in cols
    forecast_col = "forecast_serial_no" in cols
    if not serial_col and not forecast_col:
        return 0
    where_parts = []
    if serial_col:
        where_parts.append("TRIM(COALESCE(serial_no, '')) IN :sns")
    if forecast_col:
        where_parts.append("TRIM(COALESCE(forecast_serial_no, '')) IN :sns")
    result = conn.execute(
        text(f"""
            UPDATE units
            SET {', '.join(set_parts)}
            WHERE {' OR '.join(where_parts)}
        """).bindparams(bindparam("sns", expanding=True)),
        {"sns": sns},
    )
    return int(result.rowcount or 0)


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

        model_val = None
        if payload.model_type is not None and str(payload.model_type).strip():
            model_val = str(payload.model_type).strip()
            _assert_model_enabled(model_val)
            
        now_val = datetime.now().strftime("%Y-%m-%d %H:%M")
        machine_row: dict[str, Any] = {}
        
        with get_engine().begin() as conn:
            # 校验流水号是否存在
            rows = _load_machine_edit_rows_by_serials(conn, [sn])
            if not rows:
                raise HTTPException(status_code=404, detail="机台不存在")
            machine_row = dict(rows[0])
            if model_val is not None:
                _validate_compatible_model_change(
                    [machine_row],
                    model_val,
                    bound_change_confirmed=payload.confirm_bound_change,
                )
                changes.append(f"机型由 {str(machine_row.get('机型') or '').strip() or '-'} 改为 {model_val}；批次号不变")

            _apply_machine_edit_updates(
                conn,
                [machine_row],
                note=note_val if payload.note is not None else None,
                model_type=model_val,
                now_val=now_val,
            )

        cache.inventory.cache_clear()
        
        if str(machine_row.get("_source") or "") == "finished_goods":
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
                content=f"修改机台 {sn}；变更内容：{', '.join(changes)}",
                serial_no=sn,
                order_no=str(machine_row.get("占用订单号") or "").strip(),
                contract_no=str(machine_row.get("合同号") or "").strip(),
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

        new_model = None
        if payload.model_type is not None and str(payload.model_type).strip():
            new_model = str(payload.model_type).strip()
            _assert_model_enabled(new_model)
            
        new_note = None
        if note_parts:
            new_note = "；".join(note_parts)
            changes.append(f"备注改为 {new_note}")
            
        now_val = datetime.now().strftime("%Y-%m-%d %H:%M")
        machine_rows: list[dict[str, Any]] = []
        row_by_sn: dict[str, dict[str, Any]] = {}
        
        with get_engine().begin() as conn:
            # 校验流水号是否存在并锁定本次修改边界
            machine_rows = _load_machine_edit_rows_by_serials(conn, sns)
            row_by_sn = {
                str(row.get("流水号") or "").strip(): row
                for row in machine_rows
                if str(row.get("流水号") or "").strip()
            }
            match_count = len(machine_rows)
            if match_count == 0:
                raise HTTPException(status_code=404, detail="未找到对应机台")
            missing_sns = [sn for sn in sns if sn not in row_by_sn]
            if missing_sns:
                preview = "、".join(missing_sns[:8])
                suffix = "等" if len(missing_sns) > 8 else ""
                raise HTTPException(status_code=404, detail=f"部分流水号不存在，请刷新后重试：{preview}{suffix}")
            if new_model is not None:
                _validate_compatible_model_change(
                    machine_rows,
                    new_model,
                    bound_change_confirmed=payload.confirm_bound_change,
                )
                changes.append(f"机型按流水号改为 {new_model}；批次号不变")

            _apply_machine_edit_updates(
                conn,
                machine_rows,
                note=new_note,
                model_type=new_model,
                now_val=now_val,
            )
                
        cache.inventory.cache_clear()
        
        fg_sns = [
            str(row.get("流水号") or "").strip()
            for row in machine_rows
            if str(row.get("_source") or "") == "finished_goods" and str(row.get("流水号") or "").strip()
        ]
        if fg_sns:
            try:
                _sync_machine_edit_to_units(fg_sns)
            except Exception as e:
                logging.error(f"Failed to sync machine batch edit to units: {e}")
        
        # Notify Go Sandbox in background
        if sns:
            background_tasks.add_task(_notify_sandbox_background, sns)
        
        if changes:
            operator_id = current_user.get("username")
            operator_name = current_user.get("name") or current_user.get("username") or "System"
            change_text = ", ".join(changes)
            append_operation_logs([
                {
                    "user_id": operator_id,
                    "username": operator_name,
                    "action_type": "批量修改",
                    "module": "机台档案",
                    "biz_type": "机台",
                    "serial_no": sn,
                    "order_no": str(row_by_sn.get(sn, {}).get("占用订单号") or "").strip(),
                    "contract_no": str(row_by_sn.get(sn, {}).get("合同号") or "").strip(),
                    "content": (
                        f"批量修改机台 {sn}；本次共 {match_count} 台；"
                        f"原机型：{str(row_by_sn.get(sn, {}).get('机型') or '').strip() or '-'}；"
                        f"目标机型：{new_model or str(row_by_sn.get(sn, {}).get('机型') or '').strip() or '-'}；"
                        f"变更内容：{change_text}"
                    ),
                }
                for sn in sns
            ])
            
        message = "已按流水号修正机型，批次号不变" if new_model is not None else f"批量更新成功，共 {match_count} 台"
        return {"message": message}
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
        manager.broadcast_from_sync({"type": "WAREHOUSE_LAYOUT_UPDATE", "layout_id": payload.layout_id})
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
        manager.broadcast_from_sync({"type": "WAREHOUSE_LAYOUT_UPDATE", "layout_id": payload.layout_id})
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
            text("SELECT * FROM finished_goods_data WHERE `流水号` IN :sns FOR UPDATE")
            .bindparams(bindparam("sns", expanding=True))
        )
        update_stmt = (
            text(
                "UPDATE finished_goods_data "
                "SET `状态`='已出库', `更新时间`=:now_text "
                "WHERE `流水号` IN :sns "
                "AND TRIM(COALESCE(`状态`, '')) <> '已出库' "
                "AND TRIM(COALESCE(`状态`, '')) <> '报废'"
            )
            .bindparams(bindparam("sns", expanding=True))
        )

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
        with get_engine().begin() as conn:
            hit_rows = conn.execute(select_stmt, {"sns": sns}).mappings().all()
            if not hit_rows:
                raise HTTPException(status_code=422, detail="所选机台不存在")
            scrapped_sns = [
                str(row.get("流水号", "") or "").strip()
                for row in hit_rows
                if str(row.get("状态", "") or "").strip() == "报废"
            ]
            if scrapped_sns:
                raise HTTPException(status_code=422, detail=f"报废机台不能发货: {', '.join(scrapped_sns[:10])}")
            rows_to_ship = [
                dict(row)
                for row in hit_rows
                if str(row.get("状态", "") or "").strip() != "已出库"
            ]
            if not rows_to_ship:
                return {"message": "所选机台已发货，无需重复确认", "warning": "", "cloud_synced": 0}
            sns_to_ship = [str(row.get("流水号", "") or "").strip() for row in rows_to_ship if str(row.get("流水号", "") or "").strip()]
            conn.execute(update_stmt, {"sns": sns_to_ship, "now_text": now_text})
        cache.inventory.cache_clear()
        enqueue_wechat_batch_summary_sync("shipping_confirm_inventory")

        hit = pd.DataFrame(rows_to_ship).fillna("")
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
        append_log("正式发货", sns_to_ship, operator=current_operator)
        append_audit_log(
            module="发货复核",
            action_type="确认发货",
            biz_type="机台",
            content=f"确认发货 {len(sns_to_ship)} 台机台；流水号：{', '.join(sns_to_ship[:10])}",
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
        return {"message": f"发货完成，共 {len(sns_to_ship)} 台", "warning": cloud_warning, "cloud_synced": cloud_synced}
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


@router.get("/shipping/returned-candidates")
def get_shipping_return_candidates(
    keyword: str = Query(""),
    date: str = Query(""),
):
    try:
        kw = str(keyword or "").strip()
        date_filter = str(date or "").strip()
        where_clauses = ["TRIM(COALESCE(fg.`状态`, '')) = '已出库'"]
        params: Dict[str, Any] = {}
        if kw:
            where_clauses.append(
                "("
                "fg.`流水号` COLLATE utf8mb4_general_ci LIKE :kw COLLATE utf8mb4_general_ci OR "
                "fg.`占用订单号` COLLATE utf8mb4_general_ci LIKE :kw COLLATE utf8mb4_general_ci OR "
                "fg.`客户` COLLATE utf8mb4_general_ci LIKE :kw COLLATE utf8mb4_general_ci OR "
                "fg.`代理商` COLLATE utf8mb4_general_ci LIKE :kw COLLATE utf8mb4_general_ci OR "
                "fg.`机型` COLLATE utf8mb4_general_ci LIKE :kw COLLATE utf8mb4_general_ci"
                ")"
            )
            params["kw"] = f"%{kw}%"
        if date_filter:
            where_clauses.append("DATE(COALESCE(sh.`更新时间`, fg.`更新时间`)) = :date_filter")
            params["date_filter"] = date_filter
        where_sql = " AND ".join(where_clauses)
        with get_engine().connect() as conn:
            has_shipping_history = conn.execute(text("SHOW TABLES LIKE 'shipping_history'")).fetchone() is not None
            if has_shipping_history:
                sql = f"""
                    SELECT
                        fg.`批次号`,
                        fg.`机型`,
                        fg.`流水号`,
                        fg.`状态`,
                        fg.`预计入库时间`,
                        fg.`更新时间`,
                        fg.`占用订单号`,
                        fg.`客户`,
                        fg.`代理商`,
                        fg.`合同备注`,
                        fg.`Location_Code`,
                        fg.`合同号`,
                        DATE_FORMAT(COALESCE(sh.`更新时间`, fg.`更新时间`), '%Y-%m-%d') AS `发货日期`,
                        DATE_FORMAT(COALESCE(sh.`更新时间`, fg.`更新时间`), '%Y-%m-%d %H:%i') AS `发货时间`
                    FROM finished_goods_data fg
                    LEFT JOIN (
                        SELECT `流水号`, MAX(`更新时间`) AS `更新时间`
                        FROM shipping_history
                        GROUP BY `流水号`
                    ) sh ON sh.`流水号` COLLATE utf8mb4_general_ci = fg.`流水号` COLLATE utf8mb4_general_ci
                    WHERE {where_sql}
                    ORDER BY COALESCE(sh.`更新时间`, fg.`更新时间`) DESC, fg.`流水号` ASC
                """
            else:
                where_sql_no_history = where_sql.replace("COALESCE(sh.`更新时间`, fg.`更新时间`)", "fg.`更新时间`")
                sql = f"""
                    SELECT
                        fg.`批次号`,
                        fg.`机型`,
                        fg.`流水号`,
                        fg.`状态`,
                        fg.`预计入库时间`,
                        fg.`更新时间`,
                        fg.`占用订单号`,
                        fg.`客户`,
                        fg.`代理商`,
                        fg.`合同备注`,
                        fg.`Location_Code`,
                        fg.`合同号`,
                        DATE_FORMAT(fg.`更新时间`, '%Y-%m-%d') AS `发货日期`,
                        DATE_FORMAT(fg.`更新时间`, '%Y-%m-%d %H:%i') AS `发货时间`
                    FROM finished_goods_data fg
                    WHERE {where_sql_no_history}
                    ORDER BY fg.`更新时间` DESC, fg.`流水号` ASC
                """
            df = pd.read_sql(text(sql), conn, params=params)
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records"), "total": len(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取退换候选机台失败: {e}")


@router.post("/shipping/return")
def return_shipped_machines(
    payload: ShippingReturnPayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        sns = [str(x).strip() for x in (payload.serial_nos or []) if str(x).strip()]
        if not sns:
            raise HTTPException(status_code=422, detail="请先勾选至少 1 台机台")
        action = str(payload.action or "reallocate").strip()
        if action not in {"reallocate", "cancel_order"}:
            raise HTTPException(status_code=422, detail="退换类型仅支持重新配货或取消订单")
        reason = str(payload.reason or "").strip()
        if not reason:
            raise HTTPException(status_code=422, detail="请填写退换原因")

        now_dt = datetime.now()
        now_text = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        action_label = "取消订单" if action == "cancel_order" else "重新配货"

        impacted_order_ids: set[str] = set()
        returned_serials: list[str] = []
        released_pending_serials: list[str] = []
        units_cleared = 0
        cancelled_orders: list[str] = []
        new_status_by_order: dict[str, str] = {}

        with get_engine().begin() as conn:
            _ensure_shipping_return_history_table(conn)
            rows = conn.execute(
                text("SELECT * FROM finished_goods_data WHERE TRIM(`流水号`) IN :sns FOR UPDATE")
                .bindparams(bindparam("sns", expanding=True)),
                {"sns": sns},
            ).mappings().all()
            if not rows:
                raise HTTPException(status_code=422, detail="所选机台不存在")
            found_sns = {str(row.get("流水号") or "").strip() for row in rows}
            missing_sns = [sn for sn in sns if sn not in found_sns]
            if missing_sns:
                raise HTTPException(status_code=422, detail=f"所选机台不存在: {', '.join(missing_sns[:10])}")
            invalid_rows = [
                str(row.get("流水号") or "").strip()
                for row in rows
                if str(row.get("状态") or "").strip() != "已出库"
            ]
            if invalid_rows:
                raise HTTPException(status_code=422, detail=f"仅允许退回已出库机台: {', '.join(invalid_rows[:10])}")

            row_dicts = [dict(row) for row in rows]
            impacted_order_ids = {
                str(row.get("占用订单号") or "").strip()
                for row in row_dicts
                if str(row.get("占用订单号") or "").strip()
            }
            if action == "cancel_order" and not impacted_order_ids:
                raise HTTPException(status_code=422, detail="所选机台未绑定订单，不能执行取消订单")
            if action == "cancel_order" and len(impacted_order_ids) != 1:
                raise HTTPException(status_code=422, detail="取消订单退回一次只能处理同一个订单的机台")

            if action == "cancel_order" and impacted_order_ids:
                order_id = next(iter(impacted_order_ids))
                all_shipped_for_order = conn.execute(
                    text("""
                        SELECT `流水号`
                        FROM finished_goods_data
                        WHERE TRIM(COALESCE(`占用订单号`, '')) = :order_id
                          AND TRIM(COALESCE(`状态`, '')) = '已出库'
                    """),
                    {"order_id": order_id},
                ).fetchall()
                all_shipped_sns = {str(row[0] or "").strip() for row in all_shipped_for_order if str(row[0] or "").strip()}
                selected_set = set(sns)
                missing_return_sns = sorted(all_shipped_sns - selected_set)
                if missing_return_sns:
                    raise HTTPException(
                        status_code=422,
                        detail=f"取消订单需同时退回该订单所有已出库机台，缺少: {', '.join(missing_return_sns[:10])}"
                    )

            returned_serials = [
                str(row.get("流水号") or "").strip()
                for row in row_dicts
                if str(row.get("流水号") or "").strip()
            ]
            conn.execute(
                text("""
                    UPDATE finished_goods_data
                    SET `状态` = '待入库',
                        `占用订单号` = '',
                        `客户` = '',
                        `代理商` = '',
                        `合同号` = '',
                        `Location_Code` = '',
                        `更新时间` = :now_text
                    WHERE TRIM(`流水号`) IN :sns
                """).bindparams(bindparam("sns", expanding=True)),
                {"sns": returned_serials, "now_text": now_text},
            )

            history_rows = []
            for row in row_dicts:
                history_rows.append({
                    "sn": str(row.get("流水号") or "").strip(),
                    "order_id": str(row.get("占用订单号") or "").strip(),
                    "model": str(row.get("机型") or "").strip(),
                    "customer": str(row.get("客户") or "").strip(),
                    "agent": str(row.get("代理商") or "").strip(),
                    "contract_no": str(row.get("合同号") or "").strip(),
                    "return_type": action_label,
                    "reason": reason,
                    "before_status": str(row.get("状态") or "").strip(),
                    "after_status": "待入库",
                    "operator": current_operator,
                    "operate_time": now_dt,
                })
            conn.execute(
                text("""
                    INSERT INTO shipping_return_history (
                        `流水号`, `原订单号`, `机型`, `客户`, `代理商`, `合同号`,
                        `退回类型`, `退回原因`, `退回前状态`, `退回后状态`,
                        `操作人`, `操作时间`
                    ) VALUES (
                        :sn, :order_id, :model, :customer, :agent, :contract_no,
                        :return_type, :reason, :before_status, :after_status,
                        :operator, :operate_time
                    )
                """),
                history_rows,
            )

            units_cleared = _clear_units_for_returned_serials(conn, returned_serials)

            if action == "cancel_order" and impacted_order_ids:
                order_id = next(iter(impacted_order_ids))
                pending_rows = conn.execute(
                    text("""
                        SELECT `流水号`
                        FROM finished_goods_data
                        WHERE TRIM(COALESCE(`占用订单号`, '')) = :order_id
                          AND TRIM(COALESCE(`状态`, '')) <> '已出库'
                          AND TRIM(COALESCE(`状态`, '')) <> '报废'
                    """),
                    {"order_id": order_id},
                ).fetchall()
                released_pending_serials = [
                    str(row[0] or "").strip()
                    for row in pending_rows
                    if str(row[0] or "").strip()
                ]
                if released_pending_serials:
                    conn.execute(
                        text("""
                            UPDATE finished_goods_data
                            SET `状态` = '待入库',
                                `占用订单号` = '',
                                `客户` = '',
                                `代理商` = '',
                                `合同号` = '',
                                `Location_Code` = '',
                                `更新时间` = :now_text
                            WHERE TRIM(`流水号`) IN :sns
                        """).bindparams(bindparam("sns", expanding=True)),
                        {"sns": released_pending_serials, "now_text": now_text},
                    )
                    units_cleared += _clear_units_for_returned_serials(conn, released_pending_serials)

                conn.execute(
                    text("""
                        UPDATE sales_orders
                        SET `status` = 'deleted',
                            `delete_reason` = :reason
                        WHERE `订单号` = :order_id
                    """),
                    {"order_id": order_id, "reason": f"退换货取消订单：{reason}"},
                )
                cancelled_orders.append(order_id)

        cache.inventory.cache_clear()
        cache.orders.cache_clear()
        enqueue_wechat_batch_summary_sync("shipping_return")
        try:
            from crud.inventory import get_data, get_data_v2
            get_data.cache_clear()
            get_data_v2.cache_clear()
        except Exception:
            pass

        if action == "reallocate":
            for order_id in impacted_order_ids:
                new_status_by_order[order_id] = _recompute_order_status_after_shipping_return(order_id)
        else:
            new_status_by_order = {order_id: "deleted" for order_id in cancelled_orders}

        append_log(f"发货后退换-{action_label}", returned_serials, operator=current_operator)
        if released_pending_serials:
            append_log(f"退换取消订单释放-{','.join(cancelled_orders)}", released_pending_serials, operator=current_operator)

        append_audit_log(
            module="发货复核",
            action_type="退换货",
            biz_type="机台",
            content=(
                f"{action_label}退回 {len(returned_serials)} 台机台；"
                f"流水号：{', '.join(returned_serials[:10])}；原因：{reason}"
            ),
            user_id=current_user.get("username"),
            username=current_operator,
        )

        cloud_warning = ""
        dealer_orders = []
        if impacted_order_ids:
            try:
                dealer_orders = sync_dealer_order_statuses_by_sales_orders(list(impacted_order_ids))
            except Exception as cloud_exc:
                cloud_warning = f"本地退换已完成，但经销商/云端状态刷新失败：{cloud_exc}"

        return {
            "message": f"退回完成，共 {len(returned_serials)} 台",
            "returned": len(returned_serials),
            "released_pending": len(released_pending_serials),
            "units_cleared": units_cleared,
            "impacted_orders": [
                {"order_id": order_id, "status": status}
                for order_id, status in sorted(new_status_by_order.items())
            ],
            "cancelled_orders": cancelled_orders,
            "dealer_orders": dealer_orders,
            "warning": cloud_warning,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"退换货处理失败: {e}")


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
