from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.routes.auth import require_permissions
from crud.audit_logs import append_audit_log
from crud.dealer_orders import (
    approve_dealer_order,
    list_dealer_orders,
    mark_dealer_order_allocated,
    preview_dealer_order,
    reject_dealer_order,
)

router = APIRouter(dependencies=[Depends(require_permissions("DEALER_ORDER_REVIEW"))])


class ReviewPayload(BaseModel):
    note: str = Field(default="", max_length=1000)


class RejectPayload(BaseModel):
    reason: str = Field(default="", max_length=1000)


class AllocatePayload(BaseModel):
    allocated_qty: int = Field(default=1, ge=1)
    v7_order_no: str = Field(default="", max_length=128)


def _operator(ctx: dict) -> str:
    return str(ctx.get("name") or ctx.get("username") or "system").strip()


@router.get("/")
def list_orders(
    status: str = "",
    keyword: str = "",
    dealer_id: str = "",
    model: str = "",
    batch_no: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    try:
        return list_dealer_orders(
            status=status,
            keyword=keyword,
            dealer_id=dealer_id,
            model=model,
            batch_no=batch_no,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取经销商订单失败: {exc}")


@router.get("/{order_no}/preview")
def preview_order(order_no: str):
    try:
        return preview_dealer_order(order_no)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取订单校验失败: {exc}")


@router.post("/{order_no}/approve")
def approve_order(order_no: str, payload: ReviewPayload, request: Request, ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    operator = _operator(ctx)
    try:
        result = approve_dealer_order(order_no, reviewer=operator, note=payload.note)
        append_audit_log(
            module="经销商订单",
            action_type="审核通过",
            biz_type="订单",
            content=f"经销商订单审核通过：{order_no}",
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"message": "审核通过", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"审核通过失败: {exc}")


@router.post("/{order_no}/reject")
def reject_order(order_no: str, payload: RejectPayload, request: Request, ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    operator = _operator(ctx)
    try:
        result = reject_dealer_order(order_no, reviewer=operator, reason=payload.reason)
        append_audit_log(
            module="经销商订单",
            action_type="审核驳回",
            biz_type="订单",
            content=f"经销商订单审核驳回：{order_no}；原因：{payload.reason}",
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"message": "已驳回", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"驳回失败: {exc}")


@router.post("/{order_no}/mark-allocated")
def mark_allocated(order_no: str, payload: AllocatePayload, request: Request, ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    operator = _operator(ctx)
    try:
        result = mark_dealer_order_allocated(
            order_no,
            allocated_qty=payload.allocated_qty,
            v7_order_no=payload.v7_order_no,
            reviewer=operator,
        )
        append_audit_log(
            module="经销商订单",
            action_type="标记配货",
            biz_type="订单",
            content=f"经销商订单标记配货：{order_no}；数量：{payload.allocated_qty}；V7订单：{payload.v7_order_no}",
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"message": "已标记配货", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"标记配货失败: {exc}")
