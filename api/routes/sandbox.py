"""
FastAPI proxy for Go intelligent scheduling sandbox service.

All requests to /api/v1/sandbox/* are forwarded to the Go service
running on 127.0.0.1:3001, with V7 user identity headers injected.
"""
import os
import logging
import re
from typing import Optional

import asyncio

import httpx
import pandas as pd
import websockets
from fastapi import APIRouter, Request, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from api.routes.auth import get_current_user_token, get_current_user_context
from crud.roles import get_role_permissions
from database import get_engine

logger = logging.getLogger(__name__)

GO_SANDBOX_URL = os.environ.get("GO_SANDBOX_URL", "http://127.0.0.1:3001").rstrip("/")
GO_INTERNAL_TOKEN = os.environ.get("GO_INTERNAL_TOKEN", "")

DEFAULT_TIMEOUT = 30.0
RECOMPUTE_TIMEOUT = 120.0
LONG_RUNNING_PATHS = {"/forecast/recompute"}

router = APIRouter(prefix="", dependencies=[Depends(get_current_user_token)])


class RushOrderStatusPayload(BaseModel):
    status: str


def _build_go_headers(user_ctx: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Username": str(user_ctx.get("username") or ""),
        # FastAPI performs the public permission check before proxying. The Go
        # sandbox still has a legacy Admin/Boss route guard, so use an internal
        # effective role for accepted proxy calls while keeping the real role
        # available for diagnostics.
        "X-Role": "Admin",
        "X-Original-Role": str(user_ctx.get("role") or ""),
        "X-User-ID": str(user_ctx.get("username") or ""),
    }
    if GO_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = GO_INTERNAL_TOKEN
    return headers


def _get_timeout(path: str) -> float:
    for lp in LONG_RUNNING_PATHS:
        if path.endswith(lp):
            return RECOMPUTE_TIMEOUT
    return DEFAULT_TIMEOUT


def _translate_error(body: dict) -> dict:
    if "error" in body:
        return {"detail": body["error"]}
    return body


def _requires_edit_permission(method: str) -> bool:
    return method.upper() in {"POST", "PATCH", "PUT", "DELETE"}


def _has_any(perms: set[str], allowed: set[str]) -> bool:
    return bool(perms.intersection(allowed))


def _is_line_operator(role: str) -> bool:
    return role.strip().lower() == "lineoperator"


def _ensure_permission(user_ctx: dict, method: str, go_path: str = "") -> None:
    role = str(user_ctx.get("role") or "").strip()
    perms = set(get_role_permissions(role))
    method_upper = method.upper()
    path = str(go_path or "").strip()

    if method_upper == "GET" and path in {"/api/production-lines", "/api/batches"}:
        if _has_any(perms, {"SANDBOX_VIEW", "MOBILE_KANBAN_VIEW"}) or _is_line_operator(role):
            return
    if method_upper == "POST" and re.fullmatch(r"/api/production-lines/[^/]+/assign", path):
        if _has_any(perms, {"SANDBOX_EDIT", "MOBILE_KANBAN_ASSIGN"}) or _is_line_operator(role):
            return
    if method_upper == "POST" and re.fullmatch(r"/api/production-lines/[^/]+/manual-complete", path):
        if _has_any(perms, {"SANDBOX_EDIT", "MOBILE_KANBAN_ASSIGN"}) or _is_line_operator(role):
            return
    if method_upper == "POST" and re.fullmatch(r"/api/batches/[^/]+/import-to-finished-goods", path):
        if _has_any(perms, {"SANDBOX_EDIT", "MOBILE_KANBAN_ASSIGN"}) or _is_line_operator(role):
            return

    required = "SANDBOX_EDIT" if _requires_edit_permission(method_upper) else "SANDBOX_VIEW"
    if required not in perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=GO_SANDBOX_URL,
            timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=10.0),
        )
    return _client


async def proxy_ws(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    try:
        user_ctx = get_current_user_context(token)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    role = str(user_ctx.get("role") or "").strip()
    perms = get_role_permissions(role)
    if "SANDBOX_VIEW" not in perms:
        await websocket.close(code=4003, reason="Forbidden")
        return

    go_ws_url = GO_SANDBOX_URL.replace("http", "ws") + "/ws"
    go_headers = []
    if GO_INTERNAL_TOKEN:
        go_headers.append(("X-Internal-Token", GO_INTERNAL_TOKEN))
    go_headers.append(("X-Username", str(user_ctx.get("username") or "")))
    go_headers.append(("X-Role", str(user_ctx.get("role") or "")))

    try:
        async with websockets.connect(go_ws_url, additional_headers=go_headers) as go_ws:
            await websocket.accept()

            async def client_to_go():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await go_ws.send(data)
                except (WebSocketDisconnect, Exception):
                    pass

            async def go_to_client():
                try:
                    async for msg in go_ws:
                        await websocket.send_text(msg)
                except Exception:
                    pass

            done, pending = await asyncio.wait(
                [asyncio.create_task(client_to_go()), asyncio.create_task(go_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
    except Exception as e:
        logger.warning(f"WS proxy error: {e}")
        try:
            await websocket.close(code=1011, reason="Go service unavailable")
        except Exception:
            pass


from crud.inventory import append_import_staging_transactional
from utils.parsers import execute_import_transaction_payload


def _model_category(model_type: str, family_map: dict) -> str:
    """Determine model category using same logic as Go forecast.go:modelCategoryOf()"""
    v = model_type.strip().upper()
    if not v:
        return ""
    family = _normalize_model_family(family_map.get(v, ""))
    if family:
        return family
    if "特殊" in model_type:
        return "特殊"
    family = family_map.get(v, "")
    if family in ("SPECIAL", "特殊"):
        return "特殊"
    if "AUTO" in v or family == "AUTO":
        if "8055" in v or "7055" in v or "8060" in v:
            return "中大型AUTO"
        return "中小型AUTO"
    if "XS" in v or family == "XS":
        if "8055" in v or "7055" in v or "8060" in v:
            return "中大型XS"
        return "中小型XS"
    if v == "FH-300C":
        return "中小型G"
    if family == "G":
        return "中小型G"
    if v.endswith("G") and "G" not in v[:-1]:
        return "中小型G"
    return ""


def _normalize_model_family(value: object) -> str:
    family = str(value or "").strip()
    aliases = {
        "小机G": "中小型G",
        "小机XS": "中小型XS",
        "小机/XS": "中小型XS",
        "小机AUTO": "中小型AUTO",
        "大机XS": "中大型XS",
        "大机AUTO": "中大型AUTO",
        "SPECIAL": "特殊",
    }
    family = aliases.get(family, family)
    if family in {"中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO", "特殊"}:
        return family
    return ""


@router.api_route("/batches/{batch_id}/sync-preview", methods=["GET"])
async def sync_batch_preview(request: Request, batch_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "GET", f"/api/batches/{batch_id}/sync-preview")

    batch_code = str(request.query_params.get("batch_code", "")).strip()

    engine = get_engine()
    with engine.connect() as conn:
        batch_row = conn.execute(
            text("SELECT batch_id, status FROM batches WHERE batch_id = :bid"),
            {"bid": batch_id},
        ).fetchone()

        if batch_row is None:
            return JSONResponse(content={"detail": "批次不存在"}, status_code=404)

        unit_rows = conn.execute(
            text("SELECT model_type FROM units WHERE batch_id = :bid"),
            {"bid": batch_id},
        ).fetchall()

        model_dict_rows = conn.execute(
            text("SELECT model_name, model_family FROM model_dictionary WHERE enabled = 1")
        ).fetchall()

    family_map = {}
    for r in model_dict_rows:
        name = str(r[0] or "").strip().upper()
        family = str(r[1] or "").strip().upper()
        if name:
            family_map[name] = family

    count = 0
    for row in unit_rows:
        mt = str(row[0] or "").strip()
        cat = _model_category(mt, family_map)
        if cat != "":
            count += 1

    if count == 0:
        return JSONResponse(content={"count": 0, "first_serial": "", "last_serial": ""})

    month_part = "01"
    if batch_code and "-" in batch_code:
        month_part = batch_code.split("-")[0]
    elif batch_code:
        month_part = batch_code

    target_prefix = f"96-{month_part}-"

    with engine.connect() as conn:
        plan_max = conn.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(`流水号`, LENGTH(:prefix) + 1) AS UNSIGNED)), 0) "
                "FROM plan_import WHERE `流水号` LIKE :like_prefix"
            ),
            {"prefix": target_prefix, "like_prefix": f"{target_prefix}%"},
        ).scalar() or 0

        fg_max = conn.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(`流水号`, LENGTH(:prefix) + 1) AS UNSIGNED)), 0) "
                "FROM finished_goods_data WHERE `流水号` LIKE :like_prefix"
            ),
            {"prefix": target_prefix, "like_prefix": f"{target_prefix}%"},
        ).scalar() or 0

        units_max = conn.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(forecast_serial_no, LENGTH(:prefix) + 1) AS UNSIGNED)), 0) "
                "FROM units WHERE forecast_serial_no LIKE :like_prefix"
            ),
            {"prefix": target_prefix, "like_prefix": f"{target_prefix}%"},
        ).scalar() or 0

        max_seq = max(int(plan_max), int(fg_max), int(units_max))

    first_seq = max_seq + 1
    last_seq = max_seq + count
    first_sn = f"{target_prefix}{first_seq:02d}"
    last_sn = f"{target_prefix}{last_seq:02d}"

    return JSONResponse(content={
        "count": count,
        "first_serial": first_sn,
        "last_serial": last_sn,
    })


@router.api_route("/batches/last-batch-code", methods=["GET"])
async def last_batch_code(request: Request):
    """Return the last used batch_code (MM-SS) for hint in confirm dialog.
    Looks up finished_goods_data: find the record with the highest 流水号,
    then return its 批次号 as the reference for the next batch.
    """
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "GET", "/api/batches/last-batch-code")

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT `批次号` FROM finished_goods_data "
                "WHERE `批次号` IS NOT NULL AND `批次号` != '' "
                "ORDER BY `流水号` DESC LIMIT 1"
            ),
        ).fetchone()
        last_code = str(row[0]).strip() if row and row[0] else ""
        return JSONResponse(content={"last_batch_code": last_code})


@router.api_route("/batches/{batch_id}/revoke", methods=["POST"])
async def revoke_batch(request: Request, batch_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", f"/api/batches/{batch_id}/revoke")

    engine = get_engine()
    # Delete plan_import records for this batch's batch_code
    with engine.connect() as conn:
        batch_row = conn.execute(
            text("SELECT batch_code FROM batches WHERE batch_id = :bid"),
            {"bid": batch_id},
        ).fetchone()

        if batch_row is None:
            return JSONResponse(content={"detail": "批次不存在"}, status_code=404)

        batch_code = str(batch_row[0] or "").strip()
        if batch_code:
            conn.execute(
                text("DELETE FROM plan_import WHERE `批次号` = :bc"),
                {"bc": batch_code},
            )
        conn.execute(
            text("UPDATE units SET forecast_serial_no = NULL WHERE batch_id = :bid"),
            {"bid": batch_id},
        )
        conn.commit()

    # Forward revoke to Go
    go_headers = _build_go_headers(user_ctx)
    go_headers["Content-Type"] = "application/json"
    client = await _get_client()
    try:
        resp = await client.request(
            method="POST",
            url=f"/api/batches/{batch_id}/revoke",
            headers=go_headers,
            content=b"{}",
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", "Go revoke failed")
            except Exception:
                detail = resp.text or "Go revoke failed"
            return JSONResponse(content={"detail": detail}, status_code=resp.status_code)
    except httpx.ConnectError:
        return JSONResponse(content={"detail": "沙盘服务不可用"}, status_code=503)

    return JSONResponse(content={"success": True})


@router.api_route("/batches/{batch_id}/sync-to-plan", methods=["POST"])
async def sync_batch_to_plan(request: Request, batch_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", f"/api/batches/{batch_id}/sync-to-plan")

    body = {}
    try:
        body = await request.json() or {}
    except Exception:
        pass
    batch_code = str(body.get("batch_code", "")).strip()

    engine = get_engine()

    with engine.connect() as conn:
        batch_row = conn.execute(
            text(
                "SELECT batch_id, status, model_type, "
                "COALESCE(expected_inbound_date, due_date_end) AS inbound_date "
                "FROM batches WHERE batch_id = :bid"
            ),
            {"bid": batch_id},
        ).fetchone()

        if batch_row is None:
            return JSONResponse(content={"detail": "批次不存在"}, status_code=404)

        batch_status = str(batch_row[1] or "")
        if batch_status != "Confirmed":
            return JSONResponse(content={"detail": "批次尚未审核确认，无法同步"}, status_code=400)

        inbound_date = batch_row[3]
        inbound_date_str = ""
        if inbound_date is not None:
            if hasattr(inbound_date, "strftime"):
                inbound_date_str = inbound_date.strftime("%Y-%m-%d")
            else:
                inbound_date_str = str(inbound_date)[:10]

        unit_rows = conn.execute(
            text(
                "SELECT unit_id, model_type, contract_no, customer, dealer_name, due_date, order_remark, forecast_serial_no "
                "FROM units WHERE batch_id = :bid ORDER BY slot_index ASC"
            ),
            {"bid": batch_id},
        ).fetchall()

        model_dict_rows = conn.execute(
            text("SELECT model_name, model_family FROM model_dictionary WHERE enabled = 1")
        ).fetchall()

    family_map = {}
    for r in model_dict_rows:
        name = str(r[0] or "").strip().upper()
        family = str(r[1] or "").strip().upper()
        if name:
            family_map[name] = family

    # Filter: skip uncategorized models only
    filtered = []
    for row in unit_rows:
        mt = str(row[1] or "").strip()
        cat = _model_category(mt, family_map)
        if cat == "":
            continue
        filtered.append(row)

    if not filtered:
        return JSONResponse(
            content={"success": True, "count": 0, "message": "该批次无可同步卡片"},
            status_code=200,
        )

    # Generate serial numbers: 96-{month}-{seq}
    month_part = "01"
    if batch_code and "-" in batch_code:
        month_part = batch_code.split("-")[0]
    elif batch_code:
        month_part = batch_code

    target_prefix = f"96-{month_part}-"

    with engine.connect() as conn:
        plan_max = conn.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(`流水号`, LENGTH(:prefix) + 1) AS UNSIGNED)), 0) "
                "FROM plan_import WHERE `流水号` LIKE :like_prefix"
            ),
            {"prefix": target_prefix, "like_prefix": f"{target_prefix}%"},
        ).scalar() or 0

        fg_max = conn.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(`流水号`, LENGTH(:prefix) + 1) AS UNSIGNED)), 0) "
                "FROM finished_goods_data WHERE `流水号` LIKE :like_prefix"
            ),
            {"prefix": target_prefix, "like_prefix": f"{target_prefix}%"},
        ).scalar() or 0

        units_max = conn.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(forecast_serial_no, LENGTH(:prefix) + 1) AS UNSIGNED)), 0) "
                "FROM units WHERE forecast_serial_no LIKE :like_prefix"
            ),
            {"prefix": target_prefix, "like_prefix": f"{target_prefix}%"},
        ).scalar() or 0

        max_seq = max(int(plan_max), int(fg_max), int(units_max))

    records = []
    serial_pairs = []
    next_seq = max_seq + 1
    for row in filtered:
        unit_id = str(row[0] or "").strip()
        mt = str(row[1] or "").strip()
        customer = str(row[3] or "").strip()
        dealer_name = str(row[4] or "").strip()
        order_remark = str(row[6] or "").strip()
        contract_no = str(row[2] or "").strip()
        existing_sn = str(row[7] or "").strip()
        if existing_sn.startswith(target_prefix):
            sn = existing_sn
        else:
            sn = f"{target_prefix}{next_seq:02d}"
            next_seq += 1

        records.append({
            "流水号": sn,
            "批次号": batch_code,
            "机型": mt,
            "状态": "待入库",
            "预计入库时间": inbound_date_str,
            "客户": customer,
            "代理商": dealer_name,
            "合同备注": order_remark,
            "合同号": contract_no,
        })
        if unit_id:
            serial_pairs.append((unit_id, sn))

    df = pd.DataFrame(records)
    result = append_import_staging_transactional(df)

    if not result.get("ok"):
        return JSONResponse(
            content={"detail": result.get("message", "写入plan_import失败")},
            status_code=500,
        )

    units_written = 0
    if serial_pairs:
        with engine.begin() as conn:
            for unit_id, sn in serial_pairs:
                updated = conn.execute(
                    text(
                        "UPDATE units "
                        "SET forecast_serial_no = :sn "
                        "WHERE unit_id = :uid "
                        "AND batch_id = :bid"
                    ),
                    {"sn": sn, "uid": unit_id, "bid": batch_id},
                )
                units_written += int(updated.rowcount or 0)

    inserted = result.get("inserted", len(records))
    return JSONResponse(content={"success": True, "count": inserted, "units_written": units_written})


@router.api_route("/batches/{batch_id}/import-to-finished-goods", methods=["POST"])
async def import_batch_to_finished_goods(request: Request, batch_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", f"/api/batches/{batch_id}/import-to-finished-goods")

    engine = get_engine()

    with engine.connect() as conn:
        batch_row = conn.execute(
            text(
                "SELECT batch_code, "
                "COALESCE(expected_inbound_date, due_date_end) AS inbound_date "
                "FROM batches WHERE batch_id = :bid"
            ),
            {"bid": batch_id},
        ).fetchone()

        if batch_row is None:
            return JSONResponse(content={"detail": "批次不存在"}, status_code=404)

        batch_code = str(batch_row[0] or "").strip()
        if not batch_code:
            return JSONResponse(
                content={"success": True, "count": 0, "message": "批次无batch_code"},
                status_code=200,
            )

        inbound_date_val = batch_row[1]
        fallback_date = ""
        if inbound_date_val is not None:
            if hasattr(inbound_date_val, "strftime"):
                fallback_date = inbound_date_val.strftime("%Y-%m-%d")
            else:
                fallback_date = str(inbound_date_val)[:10]

        plan_rows = conn.execute(
            text(
                "SELECT `流水号`, `预计入库时间` FROM plan_import "
                "WHERE `批次号` = :bc"
            ),
            {"bc": batch_code},
        ).fetchall()

    if not plan_rows:
        return JSONResponse(
            content={"success": True, "count": 0, "message": "plan_import中无该批次记录"},
            status_code=200,
        )

    payload = []
    for row in plan_rows:
        sn = str(row[0] or "").strip()
        if not sn:
            continue
        date_str = ""
        if row[1] is not None:
            if hasattr(row[1], "strftime"):
                date_str = row[1].strftime("%Y-%m-%d")
            else:
                date_str = str(row[1])[:10]
        if not date_str:
            date_str = fallback_date
        payload.append({"trackNo": sn, "expectInDate": date_str})

    if not payload:
        return JSONResponse(
            content={"success": True, "count": 0, "message": "无有效流水号"},
            status_code=200,
        )

    result = execute_import_transaction_payload(payload, retry_times=1)
    success_count = len(result.get("success", []))
    failed_count = len(result.get("failed", []))

    return JSONResponse(content={
        "success": True,
        "count": success_count,
        "failed_count": failed_count,
    })


@router.api_route("/batches{path:path}", methods=["GET", "POST", "PATCH"])
async def proxy_batches(request: Request, path: str):
    return await _forward(request, f"/api/batches{path}")


@router.api_route("/rush-orders", methods=["GET"])
async def list_rush_orders(request: Request):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "GET", "/api/rush-orders")
    status_filter = str(request.query_params.get("status", "pending") or "pending").strip()
    params = {"status": status_filter}
    where_sql = "WHERE `status` = :status" if status_filter else ""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT
                    id,
                    contract_no,
                    customer,
                    dealer_name,
                    model_type,
                    DATE_FORMAT(due_date, '%Y-%m-%d') AS due_date,
                    source,
                    status,
                    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
                    DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s') AS updated_at
                FROM rush_order_queue
                {where_sql}
                ORDER BY created_at ASC, id ASC
            """),
            params if status_filter else {},
        ).mappings().all()
    return JSONResponse(content={"data": [dict(row) for row in rows]})


@router.api_route("/rush-orders/{order_id}", methods=["PATCH"])
async def update_rush_order_status(
    request: Request,
    order_id: int,
    payload: RushOrderStatusPayload,
):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "PATCH", f"/api/rush-orders/{order_id}")
    next_status = str(payload.status or "").strip()
    if next_status not in {"pending", "inserted", "deleted"}:
        raise HTTPException(status_code=422, detail="无效的急单状态")
    with get_engine().begin() as conn:
        result = conn.execute(
            text("""
                UPDATE rush_order_queue
                SET `status` = :status,
                    `updated_by` = :updated_by
                WHERE id = :id
            """),
            {
                "id": int(order_id),
                "status": next_status,
                "updated_by": str(user_ctx.get("username") or ""),
            },
        )
    if result.rowcount <= 0:
        raise HTTPException(status_code=404, detail="急单卡不存在")
    return JSONResponse(content={"success": True})


@router.api_route("/production-queue", methods=["GET"])
async def proxy_production_queue(request: Request):
    return await _forward(request, "/api/production-queue")


@router.api_route("/model-types", methods=["GET"])
async def proxy_model_types(request: Request):
    resp = await _forward(request, "/api/model-types")
    if isinstance(resp, JSONResponse) and resp.status_code == 404:
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT model_name, model_family FROM model_dictionary "
                        "WHERE enabled = 1 "
                        "AND UPPER(TRIM(model_name)) NOT IN ('G','XS','AUTO') "
                        "ORDER BY sort_order ASC, model_name ASC"
                    )
                ).fetchall()
            model_types = []
            for r in rows:
                model_name = str(r[0]).strip()
                if not model_name:
                    continue
                family = _normalize_model_family(r[1])
                model_types.append(
                    {
                        "model_type": model_name,
                        "model_family": family,
                    }
                )
            return JSONResponse(content={"model_types": model_types}, status_code=200)
        except Exception as e:
            logger.warning(f"model-types local fallback failed: {e}")
    return resp


@router.api_route("/units/empty-containers", methods=["GET"])
async def proxy_units_empty_containers(request: Request):
    return await _forward(request, "/api/units/empty-containers")


@router.api_route("/units/swap-content", methods=["POST"])
async def proxy_units_swap_content(request: Request):
    return await _forward(request, "/api/units/swap-content")


@router.api_route("/units/rush-insert", methods=["POST"])
async def proxy_units_rush_insert(request: Request):
    return await _forward(request, "/api/units/rush-insert")


@router.api_route("/units/special-card", methods=["POST"])
async def proxy_units_special_card(request: Request):
    return await _forward(request, "/api/units/special-card")


@router.api_route("/units/{unit_id}/move-to-special", methods=["POST"])
async def proxy_units_move_to_special(request: Request, unit_id: str):
    return await _forward(request, f"/api/units/{unit_id}/move-to-special")


@router.api_route("/units/{unit_id:path}", methods=["GET", "PATCH", "POST"])
async def proxy_units(request: Request, unit_id: str):
    return await _forward(request, f"/api/units/{unit_id}")


@router.api_route("/forecast{path:path}", methods=["POST", "GET"])
async def proxy_forecast(request: Request, path: str):
    return await _forward(request, f"/api/forecast{path}")


@router.api_route("/capacity-ratio", methods=["GET", "PATCH"])
async def proxy_capacity_ratio(request: Request):
    return await _forward(request, "/api/capacity-ratio")


@router.api_route("/production-lines{path:path}", methods=["GET", "POST"])
async def proxy_production_lines(request: Request, path: str):
    return await _forward(request, f"/api/production-lines{path}")


async def _forward(request: Request, go_path: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, request.method, go_path)
    go_headers = _build_go_headers(user_ctx)

    body = None
    if request.method in ("POST", "PATCH", "PUT"):
        body = await request.body()
        if body:
            ct = request.headers.get("content-type", "")
            if "application/json" in ct or "json" in ct:
                go_headers["Content-Type"] = "application/json"
            elif ct:
                go_headers["Content-Type"] = ct

    query_string = str(request.url.query) if request.url.query else ""
    client = await _get_client()
    timeout = _get_timeout(go_path)

    try:
        resp = await client.request(
            method=request.method,
            url=go_path,
            headers=go_headers,
            content=body,
            params=dict(pair.split("=", 1) for pair in query_string.split("&") if "=" in pair) if query_string else None,
            timeout=timeout,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="沙盘服务不可用，请确认 Go 服务已启动")
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="沙盘服务响应超时，请稍后重试")

    if resp.status_code >= 400:
        try:
            translated = _translate_error(resp.json())
        except Exception:
            translated = {"detail": resp.text or f"Go service error: {resp.status_code}"}
        return JSONResponse(content=translated, status_code=resp.status_code)

    content_type = resp.headers.get("content-type", "application/json")
    return StreamingResponse(iter([resp.content]), status_code=resp.status_code, media_type=content_type)
