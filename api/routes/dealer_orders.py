from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.routes.auth import require_permissions
from crud.audit_logs import append_audit_log
from crud.cloud_attachments import (
    find_local_order_attachment,
    list_local_order_attachments,
    sync_cloud_order_attachments,
)
from crud.dealer_orders import (
    _is_finished_stock_order,
    approve_dealer_order,
    approve_dealer_order_extra_review,
    get_dealer_orders_pending_counts,
    list_dealer_orders,
    mark_dealer_order_allocated,
    mark_dealer_order_contracted,
    preview_dealer_order,
    reject_dealer_order,
    reject_dealer_order_extra_review,
    validate_dealer_order_convertible,
)
from database import get_engine
from utils.contract_ids import contract_no_exists, next_contract_no
from crud.cloud_dealer_order_sync import (
    sync_cloud_dealer_orders,
    sync_completed_dealer_orders_to_cloud,
    sync_wechat_batch_summary_to_cloud,
)
from crud.cloud_sync_outbox import (
    get_cloud_sync_event_status,
    get_cloud_sync_status,
    process_due_cloud_sync_events,
    retry_failed_cloud_sync_events,
)
from crud.sync_channels import (
    get_sync_channels_status,
    record_channel_failure,
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
    # 已废弃：路径改为按明细行 batch_no/inventory_type 自动判定，保留字段仅为兼容旧客户端。
    save_mode: str = Field(default="sandbox", max_length=32)  # sandbox | spot
    # 已废弃：转合同后统一置已规划、人工配货，不再生成急单卡/进入沙盘。
    is_rush: bool = False
    # [{model, qty, high, rowNote, batch_no, inventory_type}]
    items: List[Dict[str, Any]] = Field(default_factory=list)
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
    status: str = Field(default="all", max_length=32)
    page_size: int = Field(default=100, ge=1, le=200)
    max_pages: int = Field(default=20, ge=1, le=100)


class CompletedCloudSyncPayload(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)



def _operator(ctx: dict) -> str:
    return str(ctx.get("name") or ctx.get("username") or "system").strip()


# 云端没有行备注时会把「订单备注」复制到每一行明细；加高只能看明细自己的
# inventory_type/机型，用备注判断会把整单所有机型误标成加高。
HEIGHTENED_INVENTORY_TYPES = frozenset({"heightened", "heighten", "high", "tall"})


def _line_is_heightened(item: dict[str, Any]) -> bool:
    """判断经销商订单明细行是否加高（与合同草稿 _item_is_heightened 口径一致）。"""
    if str(item.get("inventory_type") or "").strip().lower() in HEIGHTENED_INVENTORY_TYPES:
        return True
    return "加高" in str(item.get("model") or "")


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


@router.get("/pending-count")
def get_pending_counts(ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    try:
        return get_dealer_orders_pending_counts()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取待审核数量失败: {exc}")


@router.get("/{order_no}/attachments")
def list_order_attachments(order_no: str):
    """本地已回传的云端合同附件列表（供审核页/合同详情查看）。"""
    try:
        return {"orderNo": order_no, "data": list_local_order_attachments(order_no)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取订单附件失败: {exc}")


@router.post("/{order_no}/attachments/sync")
def sync_order_attachments(
    order_no: str,
    request: Request,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    """立即从云端拉取该订单的合同附件；日常由拉单 worker 自动完成。"""
    operator = _operator(ctx)
    try:
        result = sync_cloud_order_attachments([{"order_no": order_no, "updated_at": ""}])
        append_audit_log(
            module="经销商订单",
            action_type="同步云端附件",
            biz_type="订单",
            content=(
                f"同步云端合同附件：{order_no}；"
                f"synced={result.get('synced')}，skipped={result.get('skipped')}，failed={result.get('failed')}"
            ),
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"orderNo": order_no, **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"同步订单附件失败: {exc}")


def _local_attachment_or_404(order_no: str, attachment_id: str) -> dict:
    attachment = find_local_order_attachment(order_no, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在或尚未回传")
    return attachment


@router.get("/{order_no}/attachments/{attachment_id}/download")
def download_order_attachment(order_no: str, attachment_id: str):
    attachment = _local_attachment_or_404(order_no, attachment_id)
    return FileResponse(
        path=attachment["absolutePath"],
        filename=attachment["fileName"],
        media_type=attachment["mimeType"],
    )


@router.get("/{order_no}/attachments/{attachment_id}/preview")
def preview_order_attachment(order_no: str, attachment_id: str):
    attachment = _local_attachment_or_404(order_no, attachment_id)
    return FileResponse(
        path=attachment["absolutePath"],
        filename=attachment["fileName"],
        media_type=attachment["mimeType"],
        content_disposition_type="inline",
    )


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
            trigger="manual",
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
    """立即推送一次库存/机型快照（与 5 分钟心跳、库存变化触发共用同一实现）。"""
    operator = _operator(ctx)
    try:
        result = sync_wechat_batch_summary_to_cloud(trigger="manual")
        append_audit_log(
            module="经销商订单",
            action_type="同步云端库存",
            biz_type="库存",
            content=(
                f"同步 wechat_batch_summary 到云端："
                f"local={result.get('local_rows')}，pushed={result.get('pushed_rows')}"
            ),
            user_id=ctx.get("username"),
            username=operator,
        )
        # 顺带处理其它已排队事件，避免失败横幅里的积压一直占着队头。
        process_due_cloud_sync_events(limit=5)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"同步云端库存失败: {exc}")


@router.get("/cloud-sync-status")
def cloud_sync_status(ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    try:
        return get_cloud_sync_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"cloud sync status failed: {exc}")


@router.post("/cloud-sync-retry")
def cloud_sync_retry(ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    try:
        queued = retry_failed_cloud_sync_events()
        processed = process_due_cloud_sync_events(limit=20)
        return {**queued, **processed}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"cloud sync retry failed: {exc}")


@router.post("/sync-completed-cloud")
def sync_completed_cloud_orders(
    payload: CompletedCloudSyncPayload,
    request: Request,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    operator = _operator(ctx)
    try:
        result = sync_completed_dealer_orders_to_cloud(limit=payload.limit, trigger="manual")
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


@router.get("/sync-channels")
def sync_channels(ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    """本地同步通道状态：与云端「同步监控 → V8 桥接上传」同一套通道口径。"""
    try:
        return get_sync_channels_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取同步通道状态失败: {exc}")


@router.post("/sync-machine-snapshot")
def sync_machine_snapshot(
    request: Request,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    """立即生成并上传一次机台快照（日常由 v8_sync 每日调度自动完成）。"""
    operator = _operator(ctx)
    try:
        from v8_sync.scheduler import run_daily

        result = run_daily()
    except Exception as exc:
        record_channel_failure("machine-snapshot", exc)
        raise HTTPException(status_code=500, detail=f"机台快照同步失败: {exc}")
    event_id = str(result.get("event_id") or "")
    event_status: dict[str, Any] | None = None
    processed: dict[str, Any] = {}
    if event_id:
        processed = process_due_cloud_sync_events(limit=5)
        event_status = get_cloud_sync_event_status(event_id)
    status = result.get("status")
    if status == "locked":
        message = "另一个机台快照任务正在执行，请稍后再试"
    elif event_status and event_status.get("status") == "synced":
        message = "机台快照已上传"
    elif event_id:
        message = "机台快照已入队，等待重试"
    else:
        message = "当日机台快照已上传，无需重复同步"
    append_audit_log(
        module="经销商订单",
        action_type="同步机台快照",
        biz_type="机台",
        content=(
            f"手动同步机台快照：status={status}，event_id={event_id}，"
            f"event_status={(event_status or {}).get('status')}，{message}"
        ),
        user_id=ctx.get("username"),
        username=operator,
    )
    return {
        **result,
        "event_status": event_status,
        "processed": processed,
        "message": message,
    }


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


@router.post("/{order_no}/extra-review/approve")
def approve_extra_review(order_no: str, payload: ReviewPayload, request: Request, ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    operator = _operator(ctx)
    try:
        result = approve_dealer_order_extra_review(order_no, reviewer=operator, note=payload.note)
        append_audit_log(
            module="经销商订单",
            action_type="附加备注复审通过",
            biz_type="订单",
            content=f"经销商订单附加备注复审通过：{order_no}",
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"message": "附加备注复审通过", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"附加备注复审通过失败: {exc}")


@router.post("/{order_no}/extra-review/reject")
def reject_extra_review(order_no: str, payload: RejectPayload, request: Request, ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW"))):
    operator = _operator(ctx)
    try:
        result = reject_dealer_order_extra_review(order_no, reviewer=operator, reason=payload.reason)
        cascade = result.get("cascade_cancel") or {}
        contract_count = len(cascade.get("cancelled_contracts") or [])
        order_count = len(cascade.get("cancelled_orders") or [])
        released_count = len(cascade.get("released_serials") or [])
        cascade_text = f"；同步取消合同 {contract_count} 个、订单 {order_count} 个、释放配货 {released_count} 台"
        append_audit_log(
            module="经销商订单",
            action_type="附加备注复审驳回",
            biz_type="订单",
            content=f"经销商订单附加备注复审驳回：{order_no}；原因：{payload.reason}{cascade_text}",
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"message": f"附加备注复审已驳回{cascade_text}", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"附加备注复审驳回失败: {exc}")


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
            content=f"经销商订单标记配货：{order_no}；数量：{payload.allocated_qty}；V8betaVer1.0订单：{payload.v7_order_no}",
            user_id=ctx.get("username"),
            username=operator,
        )
        return {"message": "已标记配货", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"标记配货失败: {exc}")


def _sync_cloud_attachments_for_order(order_no: str) -> dict[str, Any]:
    """转合同后把云端上传的合同附件拉取到本地合同目录；失败只记日志。"""
    import logging

    try:
        return sync_cloud_order_attachments([{"order_no": order_no, "updated_at": ""}])
    except Exception:
        logging.getLogger(__name__).exception("cloud attachments sync failed order=%s", order_no)
        return {}


def _attach_order_form_to_contracts(
    order_no: str,
    contract_ids: list[str],
    customer: str,
    operator: str,
) -> list[str]:
    """把系统生成的订货单作为合同附件归档到新合同。

    转合同成功后调用：取该经销商订单最新一版订货单（优先已生成的预览），
    落到每个新合同的附件目录并写入 contract_records，合同管理页即可看到。
    单个合同附件失败只记日志，不能反过来判定转合同失败。
    """
    import io
    import logging

    from core.file_manager import contract_file_exists, save_contract_file
    from crud.local_contract_drafts import latest_document

    try:
        document = latest_document(order_no, customer)
    except Exception:
        logging.getLogger(__name__).exception("dealer order %s order form document unavailable", order_no)
        return []
    if not document:
        logging.getLogger(__name__).info("dealer order %s has no contract draft, skip attaching order form", order_no)
        return []

    content, file_name = document
    saved: list[str] = []
    for raw_contract_id in contract_ids or []:
        contract_id = str(raw_contract_id or "").strip()
        if not contract_id:
            continue
        try:
            if contract_file_exists(contract_id, file_name):
                continue
            buffer = io.BytesIO(content)
            buffer.name = file_name
            ok, message = save_contract_file(
                buffer, customer, contract_id, operator, convert_to_docx=False
            )
            if ok:
                saved.append(contract_id)
            else:
                logging.getLogger(__name__).warning(
                    "order form attach failed contract=%s: %s", contract_id, message
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "order form attach raised contract=%s", contract_id
            )
    return saved


STOCK_LINE_PATH = "spot"
BATCH_LINE_PATH = "batch"
# 一张经销商订单只生成一张合同，行级保留批次/来源；合同全部置「已规划」。
CONVERT_PATH_LABEL = "按明细来源自动选路（合同已规划）"


def _clear_convert_caches() -> None:
    """转合同会改写合同、订单、库存三张视图，统一清缓存避免读到旧数据。"""
    try:
        from crud.inventory import clear_inventory_data_caches
        from crud.orders import get_orders, get_orders_v2
        from crud.planning import get_factory_plan, get_factory_plan_v2

        for fn in (get_factory_plan, get_factory_plan_v2, get_orders, get_orders_v2):
            if hasattr(fn, "cache_clear"):
                fn.cache_clear()
        clear_inventory_data_caches()
    except Exception:
        logging.getLogger(__name__).exception("dealer order convert cache clear failed")


def _source_item_for(items: list[dict], index: int, model: str) -> dict:
    """按行号优先、机型兜底，找到转合同明细对应的经销商订单行。"""
    if index < len(items):
        candidate = items[index]
        if str(candidate.get("model") or "").strip() == model:
            return candidate
    for candidate in items:
        if str(candidate.get("model") or "").strip() == model:
            return candidate
    return {}


def _line_batch_source(contract_item: dict, source_item: dict) -> tuple[str, str]:
    """取一行明细的批次/来源；前端回传了行字段就以前端为准，旧客户端回退订单行。"""
    raw_batch = contract_item.get("batch_no")
    raw_type = contract_item.get("inventory_type")
    batch_no = raw_batch if raw_batch is not None else source_item.get("batch_no")
    inventory_type = raw_type if raw_type is not None else source_item.get("inventory_type")
    return str(batch_no or "").strip(), str(inventory_type or "").strip()


def _line_path(batch_no: object, inventory_type: object) -> str:
    """库存中（含空批次）走现货；具体批次按「指定批次」处理。两条路径合同都置已规划。"""
    return (
        STOCK_LINE_PATH
        if _is_finished_stock_order(batch_no, inventory_type)
        else BATCH_LINE_PATH
    )


def _build_convert_contract(
    contract_items: list[dict],
    order_items: list[dict],
    *,
    total_note: str,
    delivery_date: str,
    customer: str,
    agent: str,
) -> dict:
    """把一张经销商订单的明细合成**一张**已规划合同。

    - 同机型同加高规格合并为一行并累加数量；
    - 行级「指定批次/来源」保留具体批次（现货行留空），配货时按批次软约束匹配；
    - 不再按批次号拆合同：拆合同会增加导入/发货/对账步骤，而当前不做自动预占。
    """
    rows: list[dict] = []
    index: dict[tuple[str, bool], int] = {}
    models: list[str] = []
    batch_nos: list[str] = []
    qty_total = 0
    for position, item in enumerate(contract_items):
        model = str(item.get("model") or "").strip()
        qty = int(item.get("qty") or 0)
        if not model or qty <= 0:
            continue
        source_item = _source_item_for(order_items, position, model)
        batch_no, inventory_type = _line_batch_source(item, source_item)
        path = _line_path(batch_no, inventory_type)
        high = bool(item.get("high")) if "high" in item else _line_is_heightened(source_item)
        row_note = str(item.get("rowNote") or "").strip()
        remark = " ".join(
            part
            for part in [
                f"[总]{total_note}" if total_note else "",
                "加高" if high else "",
                row_note,
            ]
            if part
        )
        # 现货行不写批次；批次行保留指定批次，供合同管理展示和订单配货按批次优先匹配。
        source_alloc = {} if path == STOCK_LINE_PATH else ({batch_no: qty} if batch_no else {})
        merge_key = (model, high)
        existing_index = index.get(merge_key)
        if existing_index is not None:
            existing = rows[existing_index]
            existing["排产数量"] = int(existing.get("排产数量") or 0) + qty
            if remark and remark not in str(existing.get("备注") or ""):
                existing["备注"] = " ".join(
                    [part for part in [str(existing.get("备注") or "").strip(), remark] if part]
                )
            existing_alloc = existing.get("指定批次/来源")
            if not isinstance(existing_alloc, dict):
                existing_alloc = {}
            for source_batch, source_qty in source_alloc.items():
                existing_alloc[source_batch] = int(existing_alloc.get(source_batch) or 0) + int(source_qty)
            existing["指定批次/来源"] = existing_alloc
        else:
            index[merge_key] = len(rows)
            rows.append(
                {
                    "合同号": "",
                    "机型": model,
                    "排产数量": qty,
                    "要求交期": delivery_date,
                    "状态": "",
                    "备注": remark,
                    "客户名": customer,
                    "代理商": agent,
                    "指定批次/来源": source_alloc,
                    "订单号": "",
                }
            )
        qty_total += qty
        if model not in models:
            models.append(model)
        if path == BATCH_LINE_PATH and batch_no and batch_no not in batch_nos:
            batch_nos.append(batch_no)
    return {
        "add_list": rows,
        "qty": qty_total,
        "models": models,
        "batch_nos": batch_nos,
    }


def _rollback_created_contracts(contract_ids: list[str]) -> None:
    """转合同失败补偿：删掉本次新建的合同、合同通知和尚未处理的急单卡。"""
    ids = [str(cid or "").strip() for cid in contract_ids if str(cid or "").strip()]
    if not ids:
        return
    try:
        with get_engine().begin() as conn:
            for cid in ids:
                conn.execute(text("DELETE FROM factory_plan WHERE `合同号` = :cid"), {"cid": cid})
                conn.execute(
                    text("DELETE FROM contract_notifications WHERE contract_id = :cid"),
                    {"cid": cid},
                )
                try:
                    conn.execute(
                        text(
                            "DELETE FROM rush_order_queue "
                            "WHERE `contract_no` = :cid AND `status` = 'pending'"
                        ),
                        {"cid": cid},
                    )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "rollback rush queue failed contract=%s", cid
                    )
    except Exception:
        logging.getLogger(__name__).exception("rollback created contracts failed ids=%s", ids)
    finally:
        _clear_convert_caches()


@router.post("/{order_no}/convert-to-contract")
def convert_to_contract(
    order_no: str,
    payload: ConvertToContractPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: dict = Depends(require_permissions("DEALER_ORDER_REVIEW")),
):
    """经销商订单转合同：一张订单生成一张「已规划」合同，行级保留批次/来源。

    - 库存中行 / 具体批次行都进入同一张合同，合同置「已规划」，不进入沙盘预测；
    - 行级「指定批次/来源」保留批次，供订单配货时按批次优先匹配（软约束，可改选）；
    - 之后由业务人员在「销售订单 → 导入已规划合同」建单，再到「订单配货」人工分配机台；
    - 每行备注保留单行备注口径，人工配货后写到机台合同备注。
    """
    operator = _operator(ctx)
    try:
        # 1. 锁定并校验经销商订单
        items = validate_dealer_order_convertible(order_no)

        # 2. 明细：前端回传优先，否则按订单行兜底
        contract_items: List[Dict[str, Any]] = list(payload.items or [])
        if not contract_items:
            for item in items:
                contract_items.append(
                    {
                        "model": str(item.get("model") or "").strip(),
                        "qty": int(item.get("quantity") or 1),
                        "high": _line_is_heightened(item),
                        "rowNote": "",
                        "batch_no": str(item.get("batch_no") or "").strip(),
                        "inventory_type": str(item.get("inventory_type") or "").strip(),
                    }
                )

        from api.routes.planning import _assert_models_in_dictionary, _process_contracts_batch

        model_names = [
            str(ci.get("model") or "").strip()
            for ci in contract_items
            if str(ci.get("model") or "").strip()
        ]
        _assert_models_in_dictionary(model_names)

        customer = str(payload.customer_name or "").strip() or str(items[0].get("customer_name") or "").strip()
        agent = str(payload.agent_name or "").strip() or str(items[0].get("contact_name") or "").strip()
        delivery_date = str(payload.delivery_date or "").strip() or str(items[0].get("delivery_date") or "").strip()
        total_note = str(payload.contract_note or "").strip()

        # 3. 整单合成一张合同：行级保留批次/来源，同机型同加高规格合并
        contract = _build_convert_contract(
            contract_items,
            items,
            total_note=total_note,
            delivery_date=delivery_date,
            customer=customer,
            agent=agent,
        )
        if not contract["add_list"]:
            raise HTTPException(status_code=422, detail="没有可新增记录（可能都已存在或字段不完整）")

        # 4. 合同号：沿用前端预取号；没有则服务端生成
        with get_engine().connect() as conn:
            requested = str(payload.contract_no or "").strip()
            if requested and contract_no_exists(conn, requested):
                raise HTTPException(
                    status_code=422,
                    detail=f"合同号已存在，请刷新后重新生成: {requested}",
                )
            contract_no = requested or next_contract_no(conn)
        for row in contract["add_list"]:
            row["合同号"] = contract_no

        # 5. 建合同并置「已规划」（不进入沙盘预测）；失败回滚
        current_user = ctx if isinstance(ctx, dict) else {"username": operator, "role": ""}
        try:
            _process_contracts_batch(
                add_list=contract["add_list"],
                rush_source_rows=[],
                save_mode="spot",
                is_rush=False,
                user_ctx=current_user,
                operator=operator,
                background_tasks=background_tasks,
            )
        except Exception:
            _rollback_created_contracts([contract_no])
            raise

        # 6. 回写经销商订单；机台分配仍由业务人员在订单配货手动完成
        try:
            mark_dealer_order_contracted(order_no, contract_no=contract_no, operator=operator)
        except Exception:
            _rollback_created_contracts([contract_no])
            raise

        batch_text = (
            f"；指定批次：{'、'.join(contract['batch_nos'])}（配货时优先匹配，可改选）"
            if contract["batch_nos"]
            else ""
        )
        append_audit_log(
            module="经销商订单",
            action_type="转为合同",
            biz_type="订单",
            content=(
                f"经销商订单按批次/来源自动选路转合同：{order_no} → {contract_no}；"
                f"整单一张已规划合同，待人工导入订单并配货{batch_text}"
            ),
            user_id=ctx.get("username"),
            username=operator,
        )

        order_form_contracts = _attach_order_form_to_contracts(order_no, [contract_no], customer, operator)
        cloud_attachments = _sync_cloud_attachments_for_order(order_no)

        contracts_payload = [
            {
                "contract_no": contract_no,
                "path": "auto",
                "batch_nos": contract["batch_nos"],
                "path_label": CONVERT_PATH_LABEL,
                "row_count": len(contract["add_list"]),
                "qty": contract["qty"],
                "models": contract["models"],
            }
        ]
        message = (
            f"已成功转为合同 {contract_no}；合同已置「已规划」，请在销售订单导入后人工配货"
        )
        if contract["batch_nos"]:
            message = (
                f"{message}（指定批次：{'、'.join(contract['batch_nos'])}，"
                "配货时优先匹配该批次机台，可改选）"
            )

        return {
            "message": message,
            "contract_no": contract_no,
            "contract_ids": [contract_no],
            "contracts": contracts_payload,
            "save_mode": "auto",
            "order_form_attached_contracts": order_form_contracts,
            "cloud_attachments": cloud_attachments,
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
    from crud.dealer_orders import _order_hold_batch_no, _summary_batch_no
    summary_batch = _summary_batch_no(batch_no, inventory_type)
    hold_batch = _order_hold_batch_no(batch_no, inventory_type)

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
        from crud.dealer_orders import _occupied_qty_for_pool
        held_qty = _occupied_qty_for_pool(
            conn,
            model,
            hold_batch,
            statuses=("pending", "approved"),
        )

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
