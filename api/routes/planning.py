from typing import List, Dict, Any
from urllib.parse import unquote
import base64
import re
import asyncio

import os
import uuid
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import json
from sqlalchemy import text

from config import BASE_DIR
from core.file_manager import delete_contract_file, save_contract_file
from crud.audit_logs import append_audit_log
from crud.contracts import get_contract_files
from crud.inventory import get_data
from crud.model_dictionary import is_model_enabled
from crud.planning import get_factory_plan, save_factory_plan
from crud.orders import allocate_inventory, get_orders, revert_to_inbound, save_orders
from api.routes.auth import get_current_operator_name, get_current_user_context, get_current_user_token
from utils.parsers import parse_alloc_dict
from database import get_engine

router = APIRouter(dependencies=[Depends(get_current_user_token)])


def _parse_order_need_total(row: pd.Series) -> int:
    raw = str(row.get("需求机型", "") or "")
    total = 0
    for token_raw in raw.split(";"):
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


class LinkOrderPayload(BaseModel):
    order_id: str

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
        append_audit_log(
            module="销售下单",
            action_type="新增",
            biz_type="订单",
            content=(
                f"创建订单：{order_id}；客户：{payload.客户名}；"
                f"需求机型：{str(payload.需求机型 or '').strip() or '未填写'}；"
                f"需求数量：{int(payload.需求数量)}"
            ),
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": "订单创建成功", "order_id": order_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建订单失败: {e}")


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
        return {"message": "订单更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新订单失败: {e}")


@router.get("/orders/{order_id}/allocations")
def get_order_allocations_api(order_id: str):
    try:
        order_id = str(order_id).strip()
        if not order_id:
            raise HTTPException(status_code=422, detail="订单号不能为空")
        inv_df = get_data()
        rows = inv_df[
            (inv_df["占用订单号"].astype(str) == order_id)
            & (inv_df["状态"].astype(str) != "已出库")
        ].copy()
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
    request: Request,
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
        allocate_inventory(str(order_id), customer, agent, selected, operator=current_operator)
        append_audit_log(
            module="订单配货",
            action_type="配货",
            biz_type="订单",
            content=f"为订单 {order_id} 配货 {len(selected)} 台机台；流水号：{', '.join(selected[:10])}",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": f"配货成功，已锁定 {len(selected)} 台机台"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配货失败: {e}")


@router.post("/orders/{order_id}/release")
def release_order_inventory_api(
    order_id: str,
    payload: OrderReleasePayload,
    request: Request,
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
        append_audit_log(
            module="订单配货",
            action_type="释放",
            biz_type="订单",
            content=f"释放订单 {order_id} 已配机台 {len(target_sns)} 台；流水号：{', '.join(target_sns[:10])}",
            user_id=current_user.get("username"),
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
        df_plan = get_factory_plan()
        mask = df_plan["合同号"].astype(str) == str(contract_id)
        if not mask.any():
            raise HTTPException(status_code=404, detail="合同不存在")
        df_plan.loc[mask, "状态"] = new_status
        save_factory_plan(df_plan)
        append_audit_log(
            module="合同管理",
            action_type="更新状态",
            biz_type="合同",
            content=f"合同 {contract_id} 状态更新为：{new_status}",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {"message": f"合同状态已更新为 {new_status}"}
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

        # 检查合同是否已经关联了其他订单
        existing_order = df_plan.loc[mask, "订单号"].iloc[0]
        if existing_order and str(existing_order).strip():
            raise HTTPException(status_code=400, detail=f"合同已关联订单 {existing_order}，请先解除关联")

        # 更新合同状态为"已转订单"并设置订单号
        df_plan.loc[mask, "状态"] = "已转订单"
        df_plan.loc[mask, "订单号"] = order_id
        save_factory_plan(df_plan)
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


@router.post("/contracts/batch-create")
def create_contracts_batch(
    payload: BatchContractCreatePayload,
    request: Request,
    current_operator: str = Depends(get_current_operator_name),
    current_user: dict = Depends(get_current_user_context),
):
    try:
        rows = payload.rows or []
        if not rows:
            raise HTTPException(status_code=422, detail="请至少提供 1 条合同记录")
        _assert_models_in_dictionary([str(item.机型 or "").strip() for item in rows])

        df_plan = get_factory_plan()
        now_status = "未下单"
        add_list: List[Dict[str, Any]] = []
        existed = 0
        for item in rows:
            cid = str(item.合同号 or "").strip()
            customer = str(item.客户名 or "").strip()
            model = str(item.机型 or "").strip()
            due = str(item.要求交期 or "").strip()
            if not cid or not customer or not model or not due:
                continue
            qty = int(item.排产数量)
            dup_mask = (df_plan["合同号"].astype(str) == cid) & (df_plan["机型"].astype(str) == model)
            if dup_mask.any():
                existed += 1
                continue
            add_list.append(
                {
                    "合同号": cid,
                    "机型": model,
                    "排产数量": qty,
                    "要求交期": due,
                    "状态": now_status,
                    "备注": str(item.备注 or "").strip(),
                    "客户名": customer,
                    "代理商": str(item.代理商 or "").strip(),
                    "指定批次/来源": {},
                    "订单号": "",
                }
            )

        if not add_list:
            raise HTTPException(status_code=422, detail="没有可新增记录（可能都已存在或字段不完整）")

        df_plan = pd.concat([df_plan, pd.DataFrame(add_list)], ignore_index=True)
        save_factory_plan(df_plan)
        
        # 收集新录入的所有独立合同号
        added_contract_ids = list(set([str(item["合同号"]) for item in add_list]))
        contract_ids_str = "、".join(added_contract_ids)
        
        append_audit_log(
            module="合同管理",
            action_type="批量录入",
            biz_type="合同",
            content=f"批量录入合同 {len(add_list)} 条（合同号：{contract_ids_str}）；跳过重复 {existed} 条",
            user_id=current_user.get("username"),
            username=current_operator,
        )
        return {
            "message": f"批量录入完成，新增 {len(add_list)} 条，跳过重复 {existed} 条",
            "inserted": len(add_list),
            "skipped": existed,
        }
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
        status_now = str(existing.iloc[0].get("状态", "未下单"))
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

        return {"type": "", "ext": ext}
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
