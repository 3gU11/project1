from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import time
from datetime import datetime
import random

from core.navigation import get_current_user
from crud.contracts import get_unlinked_contract_folders
from crud.inventory import get_data
from crud.orders import create_sales_order, get_orders, save_orders, get_order_by_id
from crud.planning import get_factory_plan, save_factory_plan, save_planning_record, get_planning_record
from utils.formatters import get_model_rank
from utils.parsers import parse_alloc_dict, parse_plan_map, parse_requirements, to_json_text
from utils.file_manager import save_contract_file

router = APIRouter()

class PlanningDashboardResponse(BaseModel):
    plan_list: List[Dict[str, Any]]
    order_list: List[Dict[str, Any]]
    inventory_list: List[Dict[str, Any]]

class ContractStatusRequest(BaseModel):
    status: str

class ContractSavePlanRequest(BaseModel):
    rows: List[Dict[str, Any]]
    mark_to_planned: bool = True

class OrderAllocateRequest(BaseModel):
    selected_serial_nos: List[str]

class OrderReleaseRequest(BaseModel):
    all: bool = True

@router.get("/dashboard", response_model=PlanningDashboardResponse)
async def get_planning_dashboard(current_user: str = Depends(get_current_user)):
    """获取生产统筹仪表板数据"""
    try:
        fp_df = get_factory_plan()
        orders_df = get_orders()
        inventory_df = get_data()

        # 准备合同数据
        done_df = fp_df[fp_df['状态'].isin(['已规划', '已转订单', '已下单', '已配货'])].copy()

        # 过滤掉已完结的合同
        completed_oids = set()
        if not orders_df.empty and not done_df.empty:
            linked_oids = done_df['订单号'].dropna().unique()
            for oid in linked_oids:
                if not oid: continue
                ord_row = orders_df[orders_df['订单号'] == oid]
                if not ord_row.empty:
                    req = ord_row.iloc[0]['需求数量']
                    # 这里需要实现 is_order_completed 函数
                    # 暂时简化：假设订单未完结
                    completed_oids.add(oid)

        if completed_oids:
            done_df = done_df[~done_df['订单号'].isin(completed_oids)]

        # 准备独立订单数据
        manual_orders = []
        if not orders_df.empty:
            for idx, row in orders_df.iterrows():
                oid = row['订单号']
                if not oid: continue
                # 排除已关联合同的
                if oid in set(fp_df['订单号'].dropna().unique()): continue
                # 排除已完结的（暂时简化）
                manual_orders.append(row.to_dict())

        return PlanningDashboardResponse(
            plan_list=done_df.to_dict('records'),
            order_list=manual_orders,
            inventory_list=inventory_df.to_dict('records')
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统筹数据失败: {str(e)}")

@router.post("/contract/{contract_id}/status")
async def update_contract_status(
    contract_id: str,
    request: ContractStatusRequest,
    current_user: str = Depends(get_current_user)
):
    """更新合同状态"""
    try:
        fp_df = get_factory_plan()
        if contract_id not in fp_df['合同号'].values:
            raise HTTPException(status_code=404, detail="合同不存在")

        fp_df.loc[fp_df['合同号'] == contract_id, '状态'] = request.status
        save_factory_plan(fp_df)
        return {"message": "状态更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新合同状态失败: {str(e)}")

@router.post("/contract/{contract_id}/save-plan")
async def save_contract_plan(
    contract_id: str,
    request: ContractSavePlanRequest,
    current_user: str = Depends(get_current_user)
)
:
    """保存合同规划"""
    try:
        fp_df = get_factory_plan()
        if contract_id not in fp_df['合同号'].values:
            raise HTTPException(status_code=404, detail="合同不存在")

        # 验证数据
        for row in request.rows:
            need = int(row['排产数量'])
            allocated = int(row['allocation'].get('现货(Spot)', 0))
            for qty in row['allocation'].values():
                allocated += int(qty)
            if allocated > need:
                raise HTTPException(status_code=400, detail=f"机型 {row['机型']} 分配超量")
            if allocated <= 0:
                raise HTTPException(status_code=400, detail=f"机型 {row['机型']} 还未分配来源")

        # 保存规划
        for row in request.rows:
            idx = row['row_index']
            allocation = row['allocation']
            fp_df.at[idx, '指定批次/来源'] = to_json_text(allocation)
            if request.mark_to_planned and fp_df.at[idx, '状态'] == '待规划':
                fp_df.at[idx, '状态'] = '已规划'

        save_factory_plan(fp_df)
        return {"message": "规划保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存规划失败: {str(e)}")

@router.post("/orders/{order_id}/allocate")
async def allocate_order(
    order_id: str,
    request: OrderAllocateRequest,
    current_user: str = Depends(get_current_user)
):
    """分配订单"""
    try:
        orders_df = get_orders()
        if order_id not in orders_df['订单号'].values:
            raise HTTPException(status_code=404, detail="订单不存在")

        # 这里需要实现实际的分配逻辑
        # 暂时只是保存分配记录
        save_planning_record(order_id, "分配记录", to_json_text(request.selected_serial_nos))
        return {"message": "订单分配成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分配订单失败: {str(e)}")

@router.post("/orders/{order_id}/release")
async def release_order(
    order_id: str,
    request: OrderReleaseRequest,
    current_user: str = Depends(get_current_user)
):
    """释放订单"""
    try:
        orders_df = get_orders()
        if order_id not in orders_df['订单号'].values:
            raise HTTPException(status_code=404, detail="订单不存在")

        # 这里需要实现实际的释放逻辑
        # 暂时只是标记为已释放
        return {"message": "订单释放成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"释放订单失败: {str(e)}")

@router.get("/contract/{contract_id}/files")
async def get_contract_files(
    contract_id: str,
    current_user: str = Depends(get_current_user)
):
    """获取合同附件列表"""
    try:
        # 这里需要实现文件管理逻辑
        # 暂时返回空列表
        return {"data": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")

@router.post("/contract/{contract_id}/files")
async def upload_contract_file(
    contract_id: str,
    file: UploadFile = File(...),
    customer_name: str = Form(...),
    uploader_name: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """上传合同附件"""
    try:
        # 这里需要实现文件上传逻辑
        return {"message": "文件上传成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传文件失败: {str(e)}")

@router.delete("/contract/{contract_id}/files/{file_name}")
async def delete_contract_file(
    contract_id: str,
    file_name: str,
    current_user: str = Depends(get_current_user)
):
    """删除合同附件"""
    try:
        # 这里需要实现文件删除逻辑
        return {"message": "文件删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")

@router.get("/contract/{contract_id}/files/{file_name}/preview")
async def preview_contract_file(
    contract_id: str,
    file_name: str,
    current_user: str = Depends(get_current_user)
):
    """预览合同附件"""
    try:
        # 这里需要实现文件预览逻辑
        return {"type": "html", "html": "<div>预览内容</div>"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览文件失败: {str(e)}")

@router.get("/contract/{contract_id}/files/{file_name}/download")
async def download_contract_file(
    contract_id: str,
    file_name: str,
    current_user: str = Depends(get_current_user)
):
    """下载合同附件"""
    try:
        # 这里需要实现文件下载逻辑
        return {"message": "文件下载成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")