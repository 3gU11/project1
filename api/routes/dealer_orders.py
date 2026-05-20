from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.routes.auth import require_permissions
from crud.audit_logs import append_audit_log
from crud.dealer_orders import (
    approve_dealer_order,
    list_dealer_orders,
    mark_dealer_order_allocated,
    mark_dealer_order_contracted,
    preview_dealer_order,
    reject_dealer_order,
    validate_dealer_order_convertible,
)
from crud.cloud_dealer_order_sync import (
    push_cloud_allocate,
    push_cloud_contract,
    push_cloud_review,
    sync_cloud_dealer_orders,
    sync_completed_dealer_orders_to_cloud,
    sync_wechat_batch_summary_to_cloud,
)

router = APIRouter(dependencies=[Depends(require_permissions("DEALER_ORDER_REVIEW"))])


class ReviewPayload(BaseModel):
    note: str = Field(default="", max_length=1000)


class RejectPayload(BaseModel):
    reason: str = Field(default="", max_length=1000)


class AllocatePayload(BaseModel):
    allocated_qty: int = Field(default=1, ge=1)
    v7_order_no: str = Field(default="", max_length=128)


class ConvertToContractPayload(BaseModel):
    contract_no: str = Field(default="", max_length=128)
    customer_name: str = Field(default="", max_length=255)
    agent_name: str = Field(default="", max_length=255)
    delivery_date: str = Field(default="", max_length=64)
    save_mode: str = Field(default="sandbox", max_length=32)  # sandbox | spot
    is_rush: bool = False
    items: List[Dict[str, Any]] = Field(default_factory=list)  # [{model, qty, high, rowNote}]
    contract_note: str = Field(default="", max_length=2000)


class SeedDealerOrderPayload(BaseModel):
    order_no: str = Field(default="", max_length=64)
    customer_name: str = Field(default="", max_length=255)
    contact_name: str = Field(default="", max_length=128)
    contact_phone: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=255)
    batch_no: str = Field(default="", max_length=255)
    inventory_type: str = Field(default="", max_length=32)
    quantity: int = Field(default=1, ge=1)
    delivery_date: str = Field(default="", max_length=64)
    remark: str = Field(default="", max_length=2000)
    dealer_name: str = Field(default="", max_length=255)
    dealer_id: str = Field(default="test-dealer", max_length=128)


class CloudSyncPayload(BaseModel):
    status: str = Field(default="pending", max_length=32)
    page_size: int = Field(default=100, ge=1, le=200)
    max_pages: int = Field(default=20, ge=1, le=100)


class CompletedCloudSyncPayload(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)


def _operator(ctx: dict) -> str:
    return str(ctx.get("name") or ctx.get("username") or "system").strip()


def _cloud_warning(action: str, exc: Exception) -> str:
    return f"{action}已在本地完成，但回写云端失败：{exc}"


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


@router.post("/sync-cloud")
def sync_cloud_orders(
    payload: CloudSyncPayload,
    request: Request,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    operator = _operator(ctx)
    try:
        result = sync_cloud_dealer_orders(
            status=payload.status,
            page_size=payload.page_size,
            max_pages=payload.max_pages,
        )
        append_audit_log(
            module="经销商订单",
            action_type="同步云端订单",
            biz_type="订单",
            content=(
                f"同步云端经销商订单：status={result.get('status')}，"
                f"inserted={result.get('inserted')}，updated={result.get('updated')}，skipped={result.get('skipped')}"
            ),
            user_id=ctx.get("username"),
            username=operator,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"同步云端订单失败: {exc}")


@router.post("/sync-wechat-batch-summary")
def sync_wechat_batch_summary(
    request: Request,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    operator = _operator(ctx)
    try:
        result = sync_wechat_batch_summary_to_cloud()
        append_audit_log(
            module="经销商订单",
            action_type="同步云端库存",
            biz_type="库存",
            content=(
                f"同步 wechat_batch_summary 到云端："
                f"local_rows={result.get('local_rows')}，pushed_rows={result.get('pushed_rows')}"
            ),
            user_id=ctx.get("username"),
            username=operator,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"同步云端库存失败: {exc}")


@router.post("/sync-completed-cloud")
def sync_completed_cloud_orders(
    payload: CompletedCloudSyncPayload,
    request: Request,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    operator = _operator(ctx)
    try:
        result = sync_completed_dealer_orders_to_cloud(limit=payload.limit)
        append_audit_log(
            module="经销商订单",
            action_type="同步完成状态",
            biz_type="订单",
            content=(
                f"同步本地已完成经销商订单到云端："
                f"scanned={result.get('scanned')}，pushed={result.get('pushed')}，"
                f"skipped={result.get('skipped')}，failed={len(result.get('failed') or [])}"
            ),
            user_id=ctx.get("username"),
            username=operator,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"同步完成状态失败: {exc}")


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
        warning = ""
        try:
            push_cloud_review(order_no, status="approved", reviewer=operator, note=payload.note)
        except Exception as cloud_exc:
            warning = _cloud_warning("审核通过", cloud_exc)
        return {"message": "审核通过", "warning": warning, **result}
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
        warning = ""
        try:
            push_cloud_review(order_no, status="rejected", reviewer=operator, note=payload.reason)
        except Exception as cloud_exc:
            warning = _cloud_warning("驳回", cloud_exc)
        return {"message": "已驳回", "warning": warning, **result}
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
        warning = ""
        try:
            push_cloud_allocate(order_no, operator=operator, v7_order_no=payload.v7_order_no)
        except Exception as cloud_exc:
            warning = _cloud_warning("配货", cloud_exc)
        return {"message": "已标记配货", "warning": warning, **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"标记配货失败: {exc}")


@router.post("/{order_no}/convert-to-contract")
def convert_to_contract(
    order_no: str,
    payload: ConvertToContractPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    operator = _operator(ctx)
    try:
        # 1. Validate and lock the dealer order
        items = validate_dealer_order_convertible(order_no)

        # 2. Determine contract_no
        contract_no = str(payload.contract_no or "").strip()
        if not contract_no:
            from datetime import datetime
            now = datetime.now()
            y = now.strftime("%Y")
            m = now.strftime("%m")
            d = now.strftime("%d")
            rnd = str(now.microsecond % 9000 + 1000)
            contract_no = f"HT{y}{m}{d}{rnd}"

        customer = str(payload.customer_name or "").strip() or str(items[0].get("customer_name") or "").strip()
        agent = str(payload.agent_name or "").strip() or str(items[0].get("contact_name") or "").strip()
        delivery_date = str(payload.delivery_date or "").strip() or str(items[0].get("delivery_date") or "").strip()
        save_mode = str(payload.save_mode or "sandbox").strip().lower()
        if save_mode not in {"sandbox", "spot"}:
            raise HTTPException(status_code=422, detail="save_mode 仅支持 sandbox 或 spot")

        # 3. Build contract rows from payload items or order line items
        contract_items = payload.items if payload.items else []
        if not contract_items:
            for item in items:
                contract_items.append({
                    "model": str(item.get("model") or "").strip(),
                    "qty": int(item.get("quantity") or 1),
                    "high": "加高" in str(item.get("remark") or ""),
                    "rowNote": "",
                })

        # 4. Build add_list and rush_source_rows
        from api.routes.planning import _process_contracts_batch, _assert_models_in_dictionary
        from api.routes.auth import get_current_user_context

        model_names = [str(ci.get("model") or "").strip() for ci in contract_items if str(ci.get("model") or "").strip()]
        _assert_models_in_dictionary(model_names)

        add_list: List[Dict[str, Any]] = []
        rush_source_rows: List[Dict[str, Any]] = []
        add_index_by_model: Dict[str, int] = {}

        def source_item_for(index: int, model: str) -> Dict[str, Any]:
            if index < len(items):
                candidate = items[index]
                if str(candidate.get("model") or "").strip() == model:
                    return candidate
            for candidate in items:
                if str(candidate.get("model") or "").strip() == model:
                    return candidate
            return {}

        for idx, ci in enumerate(contract_items):
            model = str(ci.get("model") or "").strip()
            qty = int(ci.get("qty") or 0)
            if not model or qty <= 0:
                continue
            high = bool(ci.get("high"))
            row_note = str(ci.get("rowNote") or "").strip()
            remark_parts = [p for p in [payload.contract_note.strip() if payload.contract_note else "", "加高" if high else "", row_note] if p]
            remark = " | ".join(remark_parts)
            source_item = source_item_for(idx, model)
            batch_no = str(source_item.get("batch_no") or "").strip()
            source_alloc = {batch_no: qty} if batch_no else {}

            existing_idx = add_index_by_model.get(model)
            if existing_idx is not None:
                existing = add_list[existing_idx]
                existing["排产数量"] = int(existing.get("排产数量") or 0) + qty
                if remark and remark not in str(existing.get("备注") or ""):
                    existing["备注"] = " | ".join([p for p in [str(existing.get("备注") or "").strip(), remark] if p])
                existing_alloc = existing.get("指定批次/来源") if isinstance(existing.get("指定批次/来源"), dict) else {}
                for batch, batch_qty in source_alloc.items():
                    existing_alloc[batch] = int(existing_alloc.get(batch) or 0) + int(batch_qty)
                existing["指定批次/来源"] = existing_alloc

                rush_source_rows[existing_idx]["qty"] = int(rush_source_rows[existing_idx].get("qty") or 0) + qty
                if remark and remark not in str(rush_source_rows[existing_idx].get("remark") or ""):
                    rush_source_rows[existing_idx]["remark"] = " | ".join(
                        [p for p in [str(rush_source_rows[existing_idx].get("remark") or "").strip(), remark] if p]
                    )
                continue

            add_index_by_model[model] = len(add_list)
            add_list.append({
                "合同号": contract_no,
                "机型": model,
                "排产数量": qty,
                "要求交期": delivery_date,
                "状态": "",
                "备注": remark,
                "客户名": customer,
                "代理商": agent,
                "指定批次/来源": source_alloc,
                "订单号": "",
            })
            rush_source_rows.append({
                "contract_no": contract_no,
                "customer": customer,
                "dealer_name": agent,
                "model_type": model,
                "due_date": delivery_date,
                "qty": qty,
                "remark": remark,
            })

        # 5. Create contracts via shared logic
        current_user = ctx if isinstance(ctx, dict) else {"username": operator, "role": ""}
        result = _process_contracts_batch(
            add_list=add_list,
            rush_source_rows=rush_source_rows,
            save_mode=save_mode,
            is_rush=bool(payload.is_rush),
            user_ctx=current_user,
            operator=operator,
            background_tasks=background_tasks,
        )

        # 6. Update dealer order
        contract_ids = result.get("contract_ids", [contract_no])
        contract_no_str = "、".join(contract_ids) if contract_ids else contract_no
        mark_dealer_order_contracted(order_no, contract_no=contract_no_str, operator=operator)
        cloud_warning = ""
        try:
            push_cloud_contract(order_no, contract_no=contract_no_str, operator=operator)
        except Exception as cloud_exc:
            cloud_warning = _cloud_warning("转合同", cloud_exc)

        append_audit_log(
            module="经销商订单",
            action_type="转为合同",
            biz_type="订单",
            content=f"经销商订单转为合同：{order_no} → {contract_no_str}；模式：{save_mode}；急单：{payload.is_rush}",
            user_id=ctx.get("username"),
            username=operator,
        )

        return {
            "message": f"已成功转为合同 {contract_no_str}",
            "warning": cloud_warning,
            "contract_no": contract_no_str,
            "save_mode": save_mode,
            **{k: v for k, v in result.items() if k not in ("message", "save_mode", "contract_ids")},
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"转为合同失败: {exc}")


@router.post("/test-seed")
def seed_test_dealer_order(
    payload: SeedDealerOrderPayload,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    """Insert a test dealer order directly into the database. For e2e testing only."""
    from database import get_engine
    from crud.dealer_orders import ensure_dealer_order_tables
    from sqlalchemy import text
    import uuid

    ensure_dealer_order_tables()
    order_no = str(payload.order_no or "").strip() or f"E2E-{uuid.uuid4().hex[:12]}"
    now = __import__("datetime").datetime.now().isoformat(sep=" ")
    model = str(payload.model or "").strip()
    batch_no = str(payload.batch_no or "FINISHED-STOCK").strip()
    inventory_type = str(payload.inventory_type or "").strip()
    quantity = max(1, int(payload.quantity or 1))

    # Determine wechat_batch_summary batch for availability check
    from crud.dealer_orders import _summary_batch_no
    summary_batch = _summary_batch_no(batch_no, inventory_type)

    with get_engine().begin() as conn:
        # Ensure wechat_batch_summary has enough quantity for approval
        existing = conn.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM wechat_batch_summary "
                "WHERE batch_no = :batch AND model = :model"
            ),
            {"batch": summary_batch, "model": model},
        ).scalar() or 0

        # Count existing pending/approved orders for this model+batch (include self)
        held_qty = conn.execute(
            text(
                "SELECT COALESCE(SUM(GREATEST(quantity - allocated_qty, 0)), 0) "
                "FROM dealer_orders "
                "WHERE batch_no = :batch AND model = :model "
                "AND status IN ('pending', 'approved') "
                "AND quantity > allocated_qty"
            ),
            {"batch": str(inventory_type).strip().lower() == "finished" and "FINISHED-STOCK" or batch_no, "model": model},
        ).scalar() or 0

        needed = max(0, (held_qty + quantity) - existing)
        if needed > 0:
            # wechat_batch_summary has dual EN+CN columns, all NOT NULL. Delete then insert.
            conn.execute(
                text("DELETE FROM wechat_batch_summary WHERE batch_no = :b AND model = :m"),
                {"b": summary_batch, "m": model},
            )
            summary_id = uuid.uuid4().hex
            conn.execute(
                text(
                    "INSERT INTO wechat_batch_summary "
                    "(summary_id, batch_no, expected_inbound_time, model, quantity, "
                    " 批次号, 预计入库时间, 机型, 数量) "
                    "VALUES (:sid, :b, NULL, :m, :q, :b, NULL, :m, :q)"
                ),
                {"sid": summary_id, "b": summary_batch, "m": model, "q": existing + needed},
            )

        conn.execute(
            text(
                "INSERT INTO dealer_orders "
                "(order_no, line_no, dealer_id, dealer_name, dealer_phone, customer_name, "
                "contact_name, contact_phone, model, batch_no, eta, inventory_type, "
                "quantity, approved_qty, allocated_qty, delivery_date, remark, status, "
                "created_at, updated_at) "
                "VALUES "
                "(:order_no, :line_no, :dealer_id, :dealer_name, '', :customer_name, "
                ":contact_name, :contact_phone, :model, :batch_no, '', :inventory_type, "
                ":quantity, 0, 0, :delivery_date, :remark, 'pending', "
                ":now, :now)"
            ),
            {
                "order_no": order_no,
                "line_no": 1,
                "dealer_id": str(payload.dealer_id or "test-dealer").strip(),
                "dealer_name": str(payload.dealer_name or "测试经销商").strip(),
                "customer_name": str(payload.customer_name or "测试客户").strip(),
                "contact_name": str(payload.contact_name or "测试联系人").strip(),
                "contact_phone": str(payload.contact_phone or "13800000000").strip(),
                "model": model,
                "batch_no": batch_no,
                "inventory_type": inventory_type,
                "quantity": quantity,
                "delivery_date": str(payload.delivery_date or "").strip(),
                "remark": str(payload.remark or "").strip(),
                "now": now,
            },
        )

    return {"message": f"测试经销商订单已创建", "order_no": order_no}
