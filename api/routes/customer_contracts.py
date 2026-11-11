"""V8 内部接口：接收售后小程序上传的合同附件。

包含两类：
1. `/customer-contracts`：单机台「东莞出货合同」（HMAC，历史/单机补充场景）；
2. `/delivery-info-uploads`：交付信息上传（待处理）。合同只含机台编号与客户信息，
   上传时不绑定订单/机台，先进入 V8 待处理队列，由操作人员查看附件后手动选择机台处理。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import text

from api.routes.delivery_info_uploads import store_pending_delivery_info
from core.file_manager import save_contract_file
from crud.delivery_info_recognition import recognize_delivery_info_upload
from database import get_engine

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_CONTRACT_BYTES = 10 * 1024 * 1024
DEFAULT_KEY_ID = "aftercare-bridge-20260929"
SIGNATURE_WINDOW_SECONDS = 300


def _clean(value: object) -> str:
    return str(value or "").strip()


def _contract_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _signing_secret() -> str:
    return _clean(os.getenv("V8_CONTRACT_PUSH_SECRET") or os.getenv("V8_SYNC_SECRET"))


def _expected_key_id() -> str:
    return _clean(os.getenv("V8_CONTRACT_PUSH_KEY_ID") or DEFAULT_KEY_ID)


def _expected_contract_id(order_no: str, serial_no: str) -> str:
    return f"DG-SHIPPING-{_clean(order_no)}-{_clean(serial_no)}"


def _verify_signature(
    *,
    key_id: str,
    timestamp: str,
    serial_no: str,
    order_no: str,
    contract_id: str,
    file_sha256: str,
    signature: str,
) -> None:
    secret = _signing_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="V8 合同推送密钥未配置")
    if _clean(key_id) != _expected_key_id():
        raise HTTPException(status_code=401, detail="合同推送 Key ID 无效")
    try:
        issued_at = int(_clean(timestamp))
    except ValueError:
        raise HTTPException(status_code=401, detail="合同推送时间戳无效")
    if abs(time.time() - issued_at) > SIGNATURE_WINDOW_SECONDS:
        raise HTTPException(status_code=401, detail="合同推送签名已过期")
    message = "\n".join(
        [
            _clean(key_id),
            str(issued_at),
            _clean(serial_no),
            _clean(order_no),
            _clean(contract_id),
            _clean(file_sha256).lower(),
        ]
    )
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, _clean(signature).lower()):
        raise HTTPException(status_code=401, detail="合同推送签名校验失败")


def _verify_delivery_info_signature(
    *,
    key_id: str,
    timestamp: str,
    client_upload_id: str,
    file_sha256: str,
    signature: str,
) -> None:
    secret = _signing_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="V8 合同推送密钥未配置")
    if _clean(key_id) != _expected_key_id():
        raise HTTPException(status_code=401, detail="合同推送 Key ID 无效")
    try:
        issued_at = int(_clean(timestamp))
    except ValueError:
        raise HTTPException(status_code=401, detail="合同推送时间戳无效")
    if abs(time.time() - issued_at) > SIGNATURE_WINDOW_SECONDS:
        raise HTTPException(status_code=401, detail="合同推送签名已过期")
    message = "\n".join(
        [
            _clean(key_id),
            str(issued_at),
            _clean(client_upload_id),
            _clean(file_sha256).lower(),
        ]
    )
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, _clean(signature).lower()):
        raise HTTPException(status_code=401, detail="合同推送签名校验失败")


def _find_customer_machine(serial_no: str) -> dict | None:
    normalized = _clean(serial_no).replace("-", "")
    if not normalized:
        return None
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT `流水号` AS serial_no, `机型` AS model, `客户` AS customer, "
                "`占用订单号` AS order_no, `合同号` AS contract_no, `状态` AS status "
                "FROM finished_goods_data "
                "WHERE REPLACE(TRIM(COALESCE(`流水号`, '')), '-', '') = :sn "
                "ORDER BY `更新时间` DESC LIMIT 1"
            ),
            {"sn": normalized},
        ).mappings().first()
    return dict(row) if row else None


def _existing_contract_file(contract_id: str, file_name: str, file_sha256: str) -> dict | None:
    if not contract_id or not file_name:
        return None
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT contract_id, file_name, file_hash, file_path, uploader, upload_time "
                "FROM contract_records "
                "WHERE contract_id = :cid AND file_name = :fn AND file_hash = :fh "
                "ORDER BY upload_time DESC LIMIT 1"
            ),
            {"cid": contract_id, "fn": file_name, "fh": file_sha256},
        ).mappings().first()
    return dict(row) if row else None


@router.post("/customer-contracts")
async def push_customer_contract(
    serial_no: str = Form(...),
    order_no: str = Form(""),
    customer_name: str = Form(""),
    uploader_name: str = Form("售后小程序"),
    accepted_at: str = Form(""),
    contract_id: str = Form(""),
    file: UploadFile = File(...),
    x_v8_sync_key_id: str = Header("", alias="X-V8-Sync-Key-Id"),
    x_v8_sync_timestamp: str = Header("", alias="X-V8-Sync-Timestamp"),
    x_v8_sync_signature: str = Header("", alias="X-V8-Sync-Signature"),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="合同文件不能为空")
    if len(content) > MAX_CONTRACT_BYTES:
        raise HTTPException(status_code=413, detail="合同文件不能超过 10 MB")
    file_name = _clean(file.filename)
    if not file_name:
        raise HTTPException(status_code=400, detail="合同文件名不能为空")
    file_sha256 = _contract_sha256(content)

    _verify_signature(
        key_id=x_v8_sync_key_id,
        timestamp=x_v8_sync_timestamp,
        serial_no=serial_no,
        order_no=order_no,
        contract_id=contract_id,
        file_sha256=file_sha256,
        signature=x_v8_sync_signature,
    )

    machine = _find_customer_machine(serial_no)
    if not machine:
        raise HTTPException(status_code=404, detail="V8 未找到该流水号对应的东莞客户机台")
    resolved_serial = _clean(machine.get("serial_no")) or _clean(serial_no)
    resolved_order = _clean(machine.get("order_no"))
    if not resolved_order:
        raise HTTPException(status_code=409, detail="该机台尚未关联原销售订单，无法挂东莞出货合同")
    if _clean(order_no) and _clean(order_no) != resolved_order:
        raise HTTPException(status_code=409, detail="推送的订单号与 V8 机台当前占用订单不一致")
    resolved_contract_id = _expected_contract_id(resolved_order, resolved_serial)
    if _clean(contract_id) and _clean(contract_id) != resolved_contract_id:
        raise HTTPException(status_code=409, detail="推送的合同号与 V8 机台约定不一致")

    existing = _existing_contract_file(resolved_contract_id, file_name, file_sha256)
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "contractId": resolved_contract_id,
            "fileName": existing.get("file_name"),
            "serialNo": resolved_serial,
            "orderNo": resolved_order,
            "customerName": _clean(machine.get("customer")) or _clean(customer_name),
            "uploader": _clean(existing.get("uploader")),
            "uploadTime": _clean(existing.get("upload_time")),
        }

    await file.seek(0)
    ok, message = await asyncio.to_thread(
        save_contract_file,
        file,
        _clean(machine.get("customer")) or _clean(customer_name) or resolved_serial,
        resolved_contract_id,
        _clean(uploader_name) or "售后小程序",
        True,
    )
    if not ok:
        raise HTTPException(status_code=422, detail=message)
    return {
        "ok": True,
        "duplicate": False,
        "contractId": resolved_contract_id,
        "fileName": file_name,
        "serialNo": resolved_serial,
        "orderNo": resolved_order,
        "customerName": _clean(machine.get("customer")) or _clean(customer_name),
        "message": message,
        "receivedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "acceptedAt": _clean(accepted_at),
    }


def _empty_recognition(warning: str = "") -> dict:
    return {
        "text": "",
        "method": "",
        "machine_nos": [],
        "raw_numbers": [],
        "machines": [],
        "candidates": [],
        "warnings": [warning] if warning else [],
        "machine_nos_text": "",
        "persisted": False,
    }


async def _auto_recognize_delivery_info(saved: dict) -> dict:
    """保存待处理记录后自动识别合同机台号；任何失败只 warning，不影响上传成功。"""
    upload_id = _clean(saved.get("uploadId"))
    file_path = _clean(saved.get("filePath"))
    if not upload_id or not file_path:
        return _empty_recognition("未获得保存后的文件路径，已跳过自动识别")
    try:
        return await asyncio.to_thread(
            recognize_delivery_info_upload,
            int(upload_id),
            file_path=file_path,
        )
    except Exception as exc:  # 识别已在 crud 层容错，这里兜底
        logger.warning("交付信息上传 #%s 自动识别失败：%s", upload_id, exc)
        return _empty_recognition(f"自动识别失败：{exc}")


@router.post("/delivery-info-uploads")
async def push_delivery_info_upload(
    client_upload_id: str = Form(...),
    customer_name: str = Form(""),
    buyer_name: str = Form(""),
    buyer_address: str = Form(""),
    machine_nos: str = Form(""),
    contract_no: str = Form(""),
    uploader_name: str = Form("售后小程序-交付信息上传"),
    file: UploadFile = File(...),
    x_v8_sync_key_id: str = Header("", alias="X-V8-Sync-Key-Id"),
    x_v8_sync_timestamp: str = Header("", alias="X-V8-Sync-Timestamp"),
    x_v8_sync_signature: str = Header("", alias="X-V8-Sync-Signature"),
):
    """接收交付信息上传（待处理）：不绑定订单/机台，进入 V8 待处理队列。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="交付信息文件不能为空")
    if len(content) > MAX_CONTRACT_BYTES:
        raise HTTPException(status_code=413, detail="交付信息文件不能超过 10 MB")
    file_name = _clean(file.filename)
    if not file_name:
        raise HTTPException(status_code=400, detail="交付信息文件名不能为空")
    file_sha256 = _contract_sha256(content)

    _verify_delivery_info_signature(
        key_id=x_v8_sync_key_id,
        timestamp=x_v8_sync_timestamp,
        client_upload_id=client_upload_id,
        file_sha256=file_sha256,
        signature=x_v8_sync_signature,
    )

    saved = store_pending_delivery_info(
        client_upload_id=client_upload_id,
        file_name=file_name,
        content=content,
        customer=customer_name,
        buyer_name=buyer_name,
        buyer_address=buyer_address,
        machine_nos=machine_nos,
        contract_no=contract_no,
        uploader=uploader_name,
    )
    # 小程序未传机台号时，保存后自动识别合同附件里的东莞机台号并回填。
    final_machine_nos = _clean(machine_nos)
    recognition = None
    if not final_machine_nos:
        recognition = await _auto_recognize_delivery_info(saved)
        final_machine_nos = _clean(recognition.get("machine_nos_text")) or final_machine_nos
    return {
        "ok": True,
        "uploadId": saved["uploadId"],
        "fileName": saved["fileName"],
        "status": "pending",
        "customerName": _clean(customer_name),
        "buyerName": _clean(buyer_name),
        "buyerAddress": _clean(buyer_address),
        "machineNos": final_machine_nos,
        "contractNo": _clean(contract_no),
        "recognition": recognition,
    }
