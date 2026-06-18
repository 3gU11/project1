"""
FastAPI proxy for Go intelligent scheduling sandbox service.

All requests to /api/v1/sandbox/* are forwarded to the Go service
running on 127.0.0.1:3001, with V8betaVer1.0 user identity headers injected.
"""
import os
import logging
import re
import json
from datetime import datetime, date, timedelta
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
LONG_RUNNING_PATHS = {"/forecast/recompute", "/api/units/rush-insert"}

router = APIRouter(prefix="", dependencies=[Depends(get_current_user_token)])


class RushOrderStatusPayload(BaseModel):
    status: str


class TransferSwapPayload(BaseModel):
    urgent_unit_id: str
    target_unit_id: str
    reason: str = ""


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


def _serial_month_from_batch_code(batch_code: str, inbound_date=None) -> str:
    """Return the numeric month segment used by generated forecast serial numbers."""
    match = re.match(r"^\s*(0[1-9]|1[0-2])(?:-\d{2})?", str(batch_code or ""))
    if match:
        return match.group(1)
    if inbound_date is not None:
        if hasattr(inbound_date, "strftime"):
            return inbound_date.strftime("%m")
        inbound_match = re.match(r"^\d{4}-(0[1-9]|1[0-2])-\d{2}", str(inbound_date))
        if inbound_match:
            return inbound_match.group(1)
    return datetime.now().strftime("%m")


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
            trust_env=False,
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
    if "SANDBOX_VIEW" not in perms and "MOBILE_KANBAN_VIEW" not in perms and not _is_line_operator(role):
        await websocket.close(code=4003, reason="Forbidden")
        return

    go_ws_url = GO_SANDBOX_URL.replace("http", "ws") + "/ws"
    go_headers = []
    if GO_INTERNAL_TOKEN:
        go_headers.append(("X-Internal-Token", GO_INTERNAL_TOKEN))
    go_headers.append(("X-Username", str(user_ctx.get("username") or "")))
    go_headers.append(("X-Role", str(user_ctx.get("role") or "")))

    try:
        async with websockets.connect(go_ws_url, additional_headers=go_headers, proxy=None) as go_ws:
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


def _major_family(model_type: str) -> str:
    token = str(model_type or "").strip().upper()
    if not token:
        return ""
    if "SPECIAL" in token:
        return "SPECIAL"
    if "AUTO" in token:
        return "AUTO"
    if "XS" in token:
        return "XS"
    return "G"


def _to_date(v: object) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _find_slot_for_displaced(conn, displaced: dict, exclude_ids: set, due_buffer_days: int = 0):
    """Search for a suitable slot for the displaced contract (must be exact same model).
    Returns (unit_id, dict) or (None, None).
    """
    displaced_due = _to_date(displaced.get("due_date"))
    if not displaced_due:
        return None, None
    displaced_model = str(displaced.get("model_type") or "").strip()
    if not displaced_model:
        return None, None

    # 1) same production line empty slots (same model, same batch timeline)
    displaced_line = displaced.get("production_line_id")
    if displaced_line:
        rows = conn.execute(
            text("""
                SELECT u.unit_id, u.model_type, u.slot_index,
                       COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE u.production_line_id = :line
                  AND TRIM(UPPER(u.model_type)) = TRIM(UPPER(:model))
                  AND (u.contract_no IS NULL OR u.contract_no = '')
                  AND u.is_locked = 0
                  AND u.unit_id NOT IN :ex
                ORDER BY u.slot_index ASC
            """),
            {"line": displaced_line, "model": displaced_model, "ex": tuple(exclude_ids) if exclude_ids else ("",)},
        ).mappings().all()
        for r in rows:
            inbound = _to_date(r.get("slot_expected_inbound"))
            if inbound and inbound > (displaced_due - timedelta(days=due_buffer_days)):
                continue
            return r["unit_id"], dict(r)

    # 2) other production line empty slots (same model)
    rows = conn.execute(
        text("""
            SELECT u.unit_id, u.model_type, u.slot_index, u.production_line_id,
                   COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound,
                   pl.line_name
            FROM units u
            JOIN batches b ON b.batch_id = u.batch_id
            LEFT JOIN production_lines pl ON pl.line_id = u.production_line_id
            WHERE u.production_line_id IS NOT NULL
              AND TRIM(UPPER(u.model_type)) = TRIM(UPPER(:model))
              AND (u.contract_no IS NULL OR u.contract_no = '')
              AND u.is_locked = 0
              AND u.unit_id NOT IN :ex
            ORDER BY u.slot_index ASC
        """),
        {"model": displaced_model, "ex": tuple(exclude_ids) if exclude_ids else ("",)},
    ).mappings().all()
    for r in rows:
        inbound = _to_date(r.get("slot_expected_inbound"))
        if inbound and inbound > (displaced_due - timedelta(days=due_buffer_days)):
            continue
        return r["unit_id"], dict(r)

    # 3) confirmed batch empty slots (same model)
    rows = conn.execute(
        text("""
            SELECT u.unit_id, u.model_type, u.slot_index, u.batch_id, b.batch_code,
                   COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
            FROM units u
            JOIN batches b ON b.batch_id = u.batch_id
            WHERE b.status = 'Confirmed'
              AND TRIM(UPPER(u.model_type)) = TRIM(UPPER(:model))
              AND (u.contract_no IS NULL OR u.contract_no = '')
              AND u.is_locked = 0
              AND u.unit_id NOT IN :ex
            ORDER BY b.batch_no ASC, u.slot_index ASC
        """),
        {"model": displaced_model, "ex": tuple(exclude_ids) if exclude_ids else ("",)},
    ).mappings().all()
    for r in rows:
        inbound = _to_date(r.get("slot_expected_inbound"))
        if inbound and inbound > (displaced_due - timedelta(days=due_buffer_days)):
            continue
        return r["unit_id"], dict(r)

    # 4) predicted batch empty slots (same model)
    rows = conn.execute(
        text("""
            SELECT u.unit_id, u.model_type, u.slot_index, u.batch_id, b.batch_code,
                   COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
            FROM units u
            JOIN batches b ON b.batch_id = u.batch_id
            WHERE b.status = 'Predicted'
              AND TRIM(UPPER(u.model_type)) = TRIM(UPPER(:model))
              AND (u.contract_no IS NULL OR u.contract_no = '')
              AND u.is_locked = 0
              AND u.unit_id NOT IN :ex
            ORDER BY b.batch_no ASC, u.slot_index ASC
        """),
        {"model": displaced_model, "ex": tuple(exclude_ids) if exclude_ids else ("",)},
    ).mappings().all()
    for r in rows:
        inbound = _to_date(r.get("slot_expected_inbound"))
        if inbound and inbound > (displaced_due - timedelta(days=due_buffer_days)):
            continue
        return r["unit_id"], dict(r)

    return None, None


@router.api_route("/units/transfer-swap", methods=["POST"])
async def transfer_swap_units(request: Request):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", "/api/units/transfer-swap")

    body = await request.json()
    urgent_id = str(body.get("urgent_unit_id", "") or "").strip()
    target_id = str(body.get("target_unit_id", "") or "").strip()
    reason = str(body.get("reason", "") or "").strip()
    if not urgent_id or not target_id:
        raise HTTPException(status_code=422, detail="unit id required")
    if urgent_id == target_id:
        raise HTTPException(status_code=422, detail="urgent and target cannot be same unit")

    due_buffer_days = 0
    actor = str(user_ctx.get("username") or "system")

    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    u.unit_id, u.model_type, u.contract_no, u.customer, u.dealer_name,
                    u.due_date, u.sales_id, u.order_remark, u.is_locked,
                    u.production_line_id,
                    COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE u.unit_id IN (:u1, :u2)
                FOR UPDATE
                """
            ),
            {"u1": urgent_id, "u2": target_id},
        ).mappings().all()
        if len(rows) != 2:
            raise HTTPException(status_code=404, detail="unit not found")

        row_map = {str(r["unit_id"]): r for r in rows}
        urgent = row_map.get(urgent_id)
        target = row_map.get(target_id)
        if urgent is None or target is None:
            raise HTTPException(status_code=404, detail="unit not found")

        urgent_contract = str(urgent.get("contract_no") or "").strip()
        target_contract = str(target.get("contract_no") or "").strip()
        if not urgent_contract:
            raise HTTPException(status_code=400, detail="urgent unit must have contract")
        if bool(urgent.get("is_locked")) or bool(target.get("is_locked")):
            raise HTTPException(status_code=400, detail="unit is locked")

        if str(urgent.get("model_type") or "").strip().upper() != str(target.get("model_type") or "").strip().upper():
            raise HTTPException(status_code=400, detail="model type mismatch, cannot swap different models")

        urgent_due = _to_date(urgent.get("due_date"))
        displaced_due = _to_date(target.get("due_date")) if target_contract else None
        urgent_slot_expected = _to_date(urgent.get("slot_expected_inbound"))
        target_slot_expected = _to_date(target.get("slot_expected_inbound"))
        same_timeline = (urgent_slot_expected and target_slot_expected and urgent_slot_expected == target_slot_expected)

        # 校验1：急单自身交期 vs 目标产线预计入库时间
        # 目标产线预计入库时间必须早于急单交期，否则急单会延期交付
        if urgent_due and target_slot_expected and not same_timeline:
            if target_slot_expected > urgent_due:
                raise HTTPException(
                    status_code=400,
                    detail=f"急单交期({urgent_due.strftime('%Y-%m-%d')})早于目标产线预计入库({target_slot_expected.strftime('%Y-%m-%d')})，调货将导致延期",
                )

        # 校验2：被置换合同交期 vs 急单原产线预计入库时间
        # 挤占后原产线预计入库时间必须早于被置换合同交期
        auto_placed_to = None  # track where displaced contract was auto-placed
        if displaced_due and urgent_slot_expected and not same_timeline:
            if urgent_slot_expected > (displaced_due - timedelta(days=due_buffer_days)):
                # Auto-find alternative slot for displaced contract (same model only)
                alt_id, alt_info = _find_slot_for_displaced(
                    conn, dict(target), {urgent_id, target_id}, due_buffer_days
                )
                if alt_id:
                    # Lock the alternative unit inside this transaction
                    conn.execute(
                        text("SELECT unit_id FROM units WHERE unit_id = :uid FOR UPDATE"),
                        {"uid": alt_id},
                    )
                    auto_placed_to = alt_id

        swap_fields = ["contract_no", "customer", "dealer_name", "due_date", "sales_id", "order_remark", "model_type"]
        urgent_vals = {k: urgent.get(k) for k in swap_fields}
        target_vals = {k: target.get(k) for k in swap_fields}

        if auto_placed_to:
            # 3-way: urgent→target, target→alt, clear urgent
            # Write target's contract to alternative slot
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=:contract_no, customer=:customer, dealer_name=:dealer_name, due_date=:due_date,
                        sales_id=:sales_id, order_remark=:order_remark, model_type=:model_type,
                        is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id
                """),
                {"unit_id": alt_id, **target_vals},
            )
            # Write urgent to target
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=:contract_no, customer=:customer, dealer_name=:dealer_name, due_date=:due_date,
                        sales_id=:sales_id, order_remark=:order_remark, model_type=:model_type,
                        is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id
                """),
                {"unit_id": target_id, **urgent_vals},
            )
            # Clear urgent original slot
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=NULL, customer=NULL, dealer_id=NULL, dealer_name=NULL,
                        due_date=NULL, sales_id=NULL, order_remark=NULL,
                        is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id
                """),
                {"unit_id": urgent_id},
            )
        else:
            # Standard 2-way swap: urgent↔target
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=:contract_no, customer=:customer, dealer_name=:dealer_name, due_date=:due_date,
                        sales_id=:sales_id, order_remark=:order_remark, model_type=:model_type,
                        is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id
                """),
                {"unit_id": urgent_id, **target_vals},
            )
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no=:contract_no, customer=:customer, dealer_name=:dealer_name, due_date=:due_date,
                        sales_id=:sales_id, order_remark=:order_remark, model_type=:model_type,
                        is_locked=0, locked_by=NULL, locked_at=NULL, updated_at=NOW()
                    WHERE unit_id=:unit_id
                """),
                {"unit_id": target_id, **urgent_vals},
            )

        detail = json.dumps(
            {
                "mode": "transfer_swap",
                "urgent_unit_id": urgent_id,
                "target_unit_id": target_id,
                "urgent_contract_before": urgent_contract,
                "target_contract_before": target_contract,
                "buffer_days": due_buffer_days,
                "reason": reason,
                "auto_placed_to": auto_placed_to,
            },
            ensure_ascii=False,
        )
        conn.execute(
            text(
                """
                INSERT INTO operation_log (actor, action, target_type, target_id, detail, created_at)
                VALUES (:actor, 'transfer_swap', 'unit', :target_id, :detail, NOW())
                """
            ),
            {"actor": actor, "target_id": target_id, "detail": detail},
        )

    return JSONResponse(content={"success": True, "buffer_days": due_buffer_days, "auto_placed_to": auto_placed_to})


@router.api_route("/units/transfer-swap/find-alternatives", methods=["POST"])
async def find_swap_alternatives(request: Request):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", "/api/units/transfer-swap/find-alternatives")

    body = await request.json()
    urgent_id = str(body.get("urgent_unit_id", "") or "").strip()
    if not urgent_id:
        raise HTTPException(status_code=422, detail="urgent_unit_id required")

    due_buffer_days = 0

    with get_engine().connect() as conn:
        urgent_row = conn.execute(
            text("""
                SELECT u.unit_id, u.model_type, u.contract_no, u.due_date, u.production_line_id,
                       COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE u.unit_id = :uid
            """),
            {"uid": urgent_id},
        ).mappings().fetchone()

        if not urgent_row:
            raise HTTPException(status_code=404, detail="urgent unit not found")

        urgent_family = _major_family(str(urgent_row.get("model_type") or ""))
        urgent_due = _to_date(urgent_row.get("due_date"))
        urgent_slot_inbound = _to_date(urgent_row.get("slot_expected_inbound"))

        # ---- 1. production line alternatives ----
        line_rows = conn.execute(
            text("""
                SELECT u.unit_id, u.model_type, u.contract_no, u.customer, u.dealer_name, u.due_date,
                       u.production_line_id, pl.line_name,
                       COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                JOIN production_lines pl ON pl.line_id = u.production_line_id
                WHERE u.production_line_id IS NOT NULL
                  AND u.unit_id != :uid
                  AND u.is_locked = 0
            """),
            {"uid": urgent_id},
        ).mappings().all()

        line_targets = []
        for r in line_rows:
            if _major_family(str(r.get("model_type") or "")) != urgent_family:
                continue
            candidate_due = _to_date(r.get("due_date"))
            candidate_inbound = _to_date(r.get("slot_expected_inbound"))
            candidate_contract = str(r.get("contract_no") or "").strip()

            if not candidate_contract:
                line_targets.append({
                    "unit_id": r["unit_id"],
                    "line_name": str(r.get("line_name") or ""),
                    "model_type": str(r.get("model_type") or ""),
                    "contract_no": "",
                    "customer": "",
                    "buffer_days": None,
                    "is_empty": True,
                })
                continue

            if urgent_slot_inbound and candidate_due:
                if urgent_slot_inbound > (candidate_due - timedelta(days=due_buffer_days)):
                    continue
            if candidate_inbound and urgent_due:
                if candidate_inbound > (urgent_due - timedelta(days=due_buffer_days)):
                    continue

            buffer = None
            if candidate_inbound and urgent_due:
                buffer = (urgent_due - candidate_inbound).days
            line_targets.append({
                "unit_id": r["unit_id"],
                "line_name": str(r.get("line_name") or ""),
                "model_type": str(r.get("model_type") or ""),
                "contract_no": candidate_contract,
                "customer": str(r.get("customer") or ""),
                "buffer_days": buffer,
                "is_empty": False,
            })

        # ---- 2. confirmed batch empty slots ----
        confirmed_raw = conn.execute(
            text("""
                SELECT u.unit_id, u.model_type, u.slot_index, u.batch_id, b.batch_code,
                       COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE b.status = 'Confirmed'
                  AND (u.contract_no IS NULL OR u.contract_no = '')
                  AND u.is_locked = 0
            """)
        ).mappings().all()

        confirmed_slots = []
        for r in confirmed_raw:
            if _major_family(str(r.get("model_type") or "")) != urgent_family:
                continue
            slot_inbound = _to_date(r.get("slot_expected_inbound"))
            if slot_inbound and urgent_due:
                if slot_inbound > (urgent_due - timedelta(days=due_buffer_days)):
                    continue
            confirmed_slots.append({
                "batch_id": r["batch_id"],
                "batch_code": str(r.get("batch_code") or ""),
                "unit_id": r["unit_id"],
                "slot_index": r.get("slot_index"),
                "model_type": str(r.get("model_type") or ""),
                "expected_inbound": str(r.get("slot_expected_inbound") or ""),
            })

        # ---- 3. predicted batch empty slots ----
        predicted_raw = conn.execute(
            text("""
                SELECT u.unit_id, u.model_type, u.slot_index, u.batch_id, b.batch_code,
                       COALESCE(b.expected_inbound_date, b.due_date_end) AS slot_expected_inbound
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE b.status = 'Predicted'
                  AND (u.contract_no IS NULL OR u.contract_no = '')
                  AND u.is_locked = 0
            """)
        ).mappings().all()

        predicted_slots = []
        for r in predicted_raw:
            if _major_family(str(r.get("model_type") or "")) != urgent_family:
                continue
            slot_inbound = _to_date(r.get("slot_expected_inbound"))
            if slot_inbound and urgent_due:
                if slot_inbound > (urgent_due - timedelta(days=due_buffer_days)):
                    continue
            predicted_slots.append({
                "batch_id": r["batch_id"],
                "batch_code": str(r.get("batch_code") or ""),
                "unit_id": r["unit_id"],
                "slot_index": r.get("slot_index"),
                "model_type": str(r.get("model_type") or ""),
                "expected_inbound": str(r.get("slot_expected_inbound") or ""),
            })

    return JSONResponse(content={
        "production_line_targets": line_targets,
        "confirmed_slots": confirmed_slots,
        "predicted_slots": predicted_slots,
    })


@router.api_route("/batches/{batch_id}/sync-preview", methods=["GET"])
async def sync_batch_preview(request: Request, batch_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "GET", f"/api/batches/{batch_id}/sync-preview")

    batch_code = str(request.query_params.get("batch_code", "")).strip()
    expected_inbound_date = str(request.query_params.get("expected_inbound_date", "")).strip()

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

    month_part = _serial_month_from_batch_code(batch_code, expected_inbound_date)
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
    """Return the latest business batch_code for confirm dialog hints."""
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "GET", "/api/batches/last-batch-code")

    engine = get_engine()
    with engine.connect() as conn:
        # The confirmation prompt should follow the real finished-goods stream.
        # Sandbox/import rows are only fallbacks because they can contain old forecast history.
        row = conn.execute(
            text(
                "SELECT TRIM(CONVERT(`批次号` USING utf8mb4)) COLLATE utf8mb4_unicode_ci AS code "
                "FROM finished_goods_data "
                "WHERE `批次号` IS NOT NULL "
                "AND TRIM(`批次号`) <> '' "
                "AND TRIM(CONVERT(`批次号` USING utf8mb4)) COLLATE utf8mb4_unicode_ci REGEXP '^[0-9]{2}-[0-9]{2}' "
                "ORDER BY `更新时间` DESC, `流水号` DESC "
                "LIMIT 1"
            ),
        ).fetchone()
        if not row:
            row = conn.execute(
                text(
                    "SELECT TRIM(CONVERT(batch_code USING utf8mb4)) COLLATE utf8mb4_unicode_ci AS code "
                    "FROM batches "
                    "WHERE batch_code IS NOT NULL "
                    "AND TRIM(batch_code) <> '' "
                    "AND TRIM(CONVERT(batch_code USING utf8mb4)) COLLATE utf8mb4_unicode_ci REGEXP '^[0-9]{2}-[0-9]{2}' "
                    "ORDER BY updated_at DESC, created_at DESC "
                    "LIMIT 1"
                ),
            ).fetchone()
        if not row:
            row = conn.execute(
                text(
                    "SELECT TRIM(CONVERT(`批次号` USING utf8mb4)) COLLATE utf8mb4_unicode_ci AS code "
                    "FROM plan_import "
                    "WHERE `批次号` IS NOT NULL "
                    "AND TRIM(`批次号`) <> '' "
                    "AND TRIM(CONVERT(`批次号` USING utf8mb4)) COLLATE utf8mb4_unicode_ci REGEXP '^[0-9]{2}-[0-9]{2}' "
                    "ORDER BY `预计入库时间` DESC, `流水号` DESC "
                    "LIMIT 1"
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

    # Generate serial numbers: 96-{month}-{seq}. Free-form batch codes use the inbound month.
    month_part = _serial_month_from_batch_code(batch_code, inbound_date)
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
                    remark,
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
    data = []
    for row in rows:
        item = dict(row)
        raw_remark = str(item.get("remark") or "")
        marker = re.search(r"(?:^|\n)__source_unit_id:([^\n]+)", raw_remark)
        if marker:
            item["source_unit_id"] = marker.group(1).strip()
            item["remark"] = re.sub(r"(?:^|\n)__source_unit_id:[^\n]+", "", raw_remark).strip()
        data.append(item)
    return JSONResponse(content={"data": data})


@router.api_route("/rush-orders/{order_id}", methods=["PATCH"])
async def update_rush_order_status(
    request: Request,
    order_id: int,
    payload: RushOrderStatusPayload,
):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "PATCH", f"/api/rush-orders/{order_id}")
    next_status = str(payload.status or "").strip()
    if next_status not in {"pending", "inserted", "deleted", "returned"}:
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
                family = _normalize_model_family(r[1]) or _model_category(model_name, {})
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


@router.api_route("/units/{unit_id}/convert-to-rush", methods=["POST"])
async def convert_unit_to_rush(request: Request, unit_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", f"/api/units/{unit_id}/convert-to-rush")
    actor = str(user_ctx.get("username") or "system").strip()

    with get_engine().begin() as conn:
        unit = conn.execute(
            text("""
                SELECT
                    u.unit_id,
                    u.contract_no,
                    u.customer,
                    u.dealer_name,
                    u.model_type,
                    DATE_FORMAT(u.due_date, '%Y-%m-%d') AS due_date,
                    u.order_remark,
                    u.is_locked,
                    b.status AS batch_status
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE u.unit_id = :uid
                FOR UPDATE
            """),
            {"uid": unit_id},
        ).mappings().fetchone()
        if not unit:
            raise HTTPException(status_code=404, detail="沙盘卡片不存在")
        if str(unit.get("batch_status") or "") != "Predicted":
            raise HTTPException(status_code=422, detail="只有待确认预测批次中的卡片可以转为急单")
        if bool(unit.get("is_locked")):
            raise HTTPException(status_code=422, detail="卡片已锁定，请先解锁再转急单")

        contract_no = str(unit.get("contract_no") or "").strip()
        model_type = str(unit.get("model_type") or "").strip()
        if not contract_no or not model_type:
            raise HTTPException(status_code=422, detail="空位或备货占位不能转为急单")

        conn.execute(
            text("""
                INSERT INTO rush_order_queue
                    (contract_no, customer, dealer_name, model_type, due_date, remark, source, status, created_by, updated_by)
                VALUES
                    (:contract_no, :customer, :dealer_name, :model_type, :due_date, :remark, 'sandbox-card', 'pending', :actor, :actor)
            """),
            {
                "contract_no": contract_no,
                "customer": str(unit.get("customer") or "").strip(),
                "dealer_name": str(unit.get("dealer_name") or "").strip(),
                "model_type": model_type,
                "due_date": str(unit.get("due_date") or "").strip() or None,
                "remark": "\n".join(
                    part for part in [
                        str(unit.get("order_remark") or "").strip(),
                        f"__source_unit_id:{unit_id}",
                    ] if part
                ),
                "actor": actor,
            },
        )
        conn.execute(
            text("""
                UPDATE units
                SET contract_no = NULL,
                    customer = NULL,
                    dealer_id = NULL,
                    dealer_name = NULL,
                    due_date = NULL,
                    sales_id = NULL,
                    order_remark = NULL,
                    is_contract_pinned = 0,
                    updated_at = NOW()
                WHERE unit_id = :uid
            """),
            {"uid": unit_id},
        )

    return JSONResponse(content={"success": True, "message": "已转为急单"})


@router.api_route("/rush-orders/{order_id}/return-to-sandbox", methods=["POST"])
async def return_rush_order_to_sandbox(request: Request, order_id: int):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", f"/api/rush-orders/{order_id}/return-to-sandbox")
    actor = str(user_ctx.get("username") or "system").strip()

    with get_engine().begin() as conn:
        rush = conn.execute(
            text("""
                SELECT
                    id,
                    contract_no,
                    customer,
                    dealer_name,
                    model_type,
                    DATE_FORMAT(due_date, '%Y-%m-%d') AS due_date,
                    remark,
                    source,
                    status
                FROM rush_order_queue
                WHERE id = :id
                FOR UPDATE
            """),
            {"id": int(order_id)},
        ).mappings().fetchone()
        if not rush:
            raise HTTPException(status_code=404, detail="急单不存在")
        if str(rush.get("status") or "") != "pending":
            raise HTTPException(status_code=422, detail="只有待处理急单可以返回沙盘")

        contract_no = str(rush.get("contract_no") or "").strip()
        model_type = str(rush.get("model_type") or "").strip()
        if not contract_no or not model_type:
            raise HTTPException(status_code=422, detail="急单缺少合同号或机型，无法返回沙盘")

        due_date = str(rush.get("due_date") or "").strip() or None
        customer = str(rush.get("customer") or "").strip()
        dealer_name = str(rush.get("dealer_name") or "").strip()
        remark = str(rush.get("remark") or "").strip()

        source = str(rush.get("source") or "").strip()
        raw_remark = str(rush.get("remark") or "")
        marker = re.search(r"(?:^|\n)__source_unit_id:([^\n]+)", raw_remark)
        source_unit_id = source.split("sandbox-card:", 1)[1].strip() if source.startswith("sandbox-card:") else ""
        if not source_unit_id and marker:
            source_unit_id = marker.group(1).strip()
        remark = re.sub(r"(?:^|\n)__source_unit_id:[^\n]+", "", raw_remark).strip()
        target_unit_id = ""

        if source_unit_id:
            source_unit = conn.execute(
                text("""
                    SELECT u.unit_id, u.batch_id, u.contract_no, u.is_locked, b.status AS batch_status
                    FROM units u
                    JOIN batches b ON b.batch_id = u.batch_id
                    WHERE u.unit_id = :uid
                    FOR UPDATE
                """),
                {"uid": source_unit_id},
            ).mappings().fetchone()
            if source_unit and str(source_unit.get("batch_status") or "") == "Predicted" \
                    and not bool(source_unit.get("is_locked")) \
                    and not str(source_unit.get("contract_no") or "").strip():
                target_unit_id = str(source_unit.get("unit_id") or "")

        if target_unit_id:
            conn.execute(
                text("""
                    UPDATE units
                    SET contract_no = :contract_no,
                        customer = :customer,
                        dealer_name = :dealer_name,
                        model_type = :model_type,
                        due_date = :due_date,
                        order_remark = :remark,
                        is_contract_pinned = 1,
                        updated_at = NOW()
                    WHERE unit_id = :uid
                """),
                {
                    "uid": target_unit_id,
                    "contract_no": contract_no,
                    "customer": customer or None,
                    "dealer_name": dealer_name or None,
                    "model_type": model_type,
                    "due_date": due_date,
                    "remark": remark or None,
                },
            )
        else:
            target_major = _major_family(model_type)
            target_batch = conn.execute(
                text("""
                    SELECT batch_id, model_type
                    FROM batches
                    WHERE status = 'Predicted'
                      AND UPPER(TRIM(COALESCE(model_type, ''))) <> 'SPECIAL'
                      AND (
                        UPPER(TRIM(model_type)) = UPPER(:model_type)
                        OR UPPER(TRIM(model_type)) = UPPER(:major)
                      )
                    ORDER BY
                      CASE
                        WHEN UPPER(TRIM(model_type)) = UPPER(:model_type) THEN 0
                        WHEN UPPER(TRIM(model_type)) = UPPER(:major) THEN 1
                        ELSE 2
                      END,
                      batch_no ASC,
                      created_at ASC
                    LIMIT 1
                    FOR UPDATE
                """),
                {"model_type": model_type, "major": target_major},
            ).mappings().fetchone()
            if not target_batch:
                raise HTTPException(status_code=422, detail="没有可返回的待确认预测沙盘列")

            max_slot = conn.execute(
                text("SELECT COALESCE(MAX(slot_index), 0) FROM units WHERE batch_id = :bid"),
                {"bid": target_batch["batch_id"]},
            ).fetchone()[0]
            next_slot = int(max_slot or 0) + 1
            unit_id = f"{target_batch['batch_id']}-S{next_slot:02d}"
            exists = conn.execute(
                text("SELECT COUNT(*) FROM units WHERE unit_id = :uid"),
                {"uid": unit_id},
            ).fetchone()[0]
            if int(exists or 0) > 0:
                unit_id = f"{target_batch['batch_id']}-R{order_id}-{next_slot}"

            conn.execute(
                text("""
                    INSERT INTO units
                        (unit_id, batch_id, slot_index, model_type, status, contract_no, customer,
                         dealer_name, due_date, order_remark, is_locked, is_contract_pinned,
                         created_at, updated_at)
                    VALUES
                        (:unit_id, :batch_id, :slot_index, :model_type, 'Pending', :contract_no, :customer,
                         :dealer_name, :due_date, :remark, 0, 1, :now, :now)
                """),
                {
                    "unit_id": unit_id,
                    "batch_id": target_batch["batch_id"],
                    "slot_index": next_slot,
                    "model_type": model_type,
                    "contract_no": contract_no,
                    "customer": customer or None,
                    "dealer_name": dealer_name or None,
                    "due_date": due_date,
                    "remark": remark or None,
                    "now": datetime.now(),
                },
            )
            target_unit_id = unit_id

        conn.execute(
            text("""
                UPDATE rush_order_queue
                SET status = 'returned',
                    updated_by = :actor
                WHERE id = :id
            """),
            {"id": int(order_id), "actor": actor},
        )
        conn.execute(
            text("""
                INSERT INTO operation_log (actor, action, target_type, target_id, detail, created_at)
                VALUES (:actor, 'rush_return_to_sandbox', 'rush_order', :target_id, :detail, NOW())
            """),
            {
                "actor": actor,
                "target_id": str(order_id),
                "detail": json.dumps(
                    {
                        "rush_order_id": int(order_id),
                        "target_unit_id": target_unit_id,
                        "contract_no": contract_no,
                        "model_type": model_type,
                    },
                    ensure_ascii=False,
                ),
            },
        )

    return JSONResponse(content={"success": True, "target_unit_id": target_unit_id})


@router.api_route("/units/special-card", methods=["POST"])
async def proxy_units_special_card(request: Request):
    return await _forward(request, "/api/units/special-card")


@router.api_route("/units/{unit_id}/move-to-special", methods=["POST"])
async def proxy_units_move_to_special(request: Request, unit_id: str):
    return await _forward(request, f"/api/units/{unit_id}/move-to-special")


@router.api_route("/units/{unit_id}/return-to-sandbox", methods=["POST"])
async def return_unit_to_sandbox(request: Request, unit_id: str):
    user_ctx = get_current_user_context(request.headers.get("Authorization", "").replace("Bearer ", ""))
    _ensure_permission(user_ctx, "POST", f"/api/units/{unit_id}/return-to-sandbox")

    body = await request.json()
    target_batch_id = str(body.get("target_batch_id", "") or "").strip()
    if not target_batch_id:
        raise HTTPException(status_code=422, detail="target_batch_id required")

    actor = str(user_ctx.get("username") or "system")

    with get_engine().begin() as conn:
        unit_row = conn.execute(
            text("""
                SELECT u.unit_id, u.production_line_id, u.batch_id, u.contract_no, u.is_locked,
                       b.status AS batch_status
                FROM units u
                JOIN batches b ON b.batch_id = u.batch_id
                WHERE u.unit_id = :uid
                FOR UPDATE
            """),
            {"uid": unit_id},
        ).mappings().fetchone()

        if not unit_row:
            raise HTTPException(status_code=404, detail="unit not found")
        if not unit_row.get("production_line_id"):
            raise HTTPException(status_code=400, detail="unit is not on a production line")

        target_batch = conn.execute(
            text("""
                SELECT batch_id, status, model_type FROM batches WHERE batch_id = :bid FOR UPDATE
            """),
            {"bid": target_batch_id},
        ).mappings().fetchone()

        if not target_batch:
            raise HTTPException(status_code=404, detail="target batch not found")
        if target_batch["status"] not in ("Confirmed", "Predicted"):
            raise HTTPException(status_code=400, detail="target batch must be Confirmed or Predicted")

        old_line = unit_row["production_line_id"]
        old_batch = unit_row["batch_id"]

        # find next available slot_index in target batch (unique constraint uq_units_batch_slot)
        max_slot = conn.execute(
            text("SELECT COALESCE(MAX(slot_index), 0) FROM units WHERE batch_id = :bid"),
            {"bid": target_batch_id},
        ).fetchone()[0]
        next_slot = int(max_slot) + 1

        conn.execute(
            text("""
                UPDATE units
                SET batch_id = :bid, slot_index = :slot, production_line_id = NULL, is_locked = 0,
                    locked_by = NULL, locked_at = NULL, status = 'Pending', updated_at = NOW()
                WHERE unit_id = :uid
            """),
            {"bid": target_batch_id, "slot": next_slot, "uid": unit_id},
        )

        # 标记历史台账记录为已撤销
        conn.execute(
            text("""
                UPDATE production_history_ledger
                SET status = 'Cancelled', completed_at = NOW()
                WHERE status = 'In_Production' AND unit_id = :uid
            """),
            {"uid": unit_id},
        )

        remaining = conn.execute(
            text("""
                SELECT COUNT(*) AS cnt FROM units
                WHERE production_line_id = :lid AND status != 'Completed'
            """),
            {"lid": old_line},
        ).fetchone()[0]

        if remaining == 0:
            conn.execute(
                text("""
                    UPDATE production_lines SET status = 'Idle', current_batch_id = NULL,
                        updated_at = NOW()
                    WHERE production_line_id = :lid
                """),
                {"lid": old_line},
            )

        detail = json.dumps({
            "mode": "return_to_sandbox",
            "unit_id": unit_id,
            "from_production_line_id": old_line,
            "from_batch_id": old_batch,
            "target_batch_id": target_batch_id,
        }, ensure_ascii=False)

        conn.execute(
            text("""
                INSERT INTO operation_log (actor, action, target_type, target_id, detail, created_at)
                VALUES (:actor, 'return_to_sandbox', 'unit', :target_id, :detail, NOW())
            """),
            {"actor": actor, "target_id": unit_id, "detail": detail},
        )

    return JSONResponse(content={"success": True})


@router.api_route("/units/{unit_id:path}", methods=["GET", "PATCH", "POST"])
async def proxy_units(request: Request, unit_id: str):
    if request.method == "POST" and unit_id == "transfer-swap":
        return await transfer_swap_units(request)
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
