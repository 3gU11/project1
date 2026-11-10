"""V8 内部接口：接收售后小程序推送的「东莞出货合同」。

背景：售后小程序在东莞交付验收时收集客户合同（PDF/照片），云端售后 Spring 以
HMAC 签名调用本接口，V8 把文件挂到客户成品管理「当前机台东莞出货合同」附件下
（contract_id = ``DG-SHIPPING-{占用订单号}-{流水号}``，与前端确认出货弹窗同一口径），
之后由 V8 人员人工确认出货。

安全：不走 V8 用户登录态，使用与云端订单同步同一套共享密钥/HMAC；签名绑定
key_id、时间戳、流水号、订单号、合同号与文件 SHA-256，时间窗 ±5 分钟。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from datetime import datetime

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import text

from core.file_manager import delete_contract_file, save_contract_file
from database import get_engine

router = APIRouter()

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


def _verify_order_signature(
    *,
    key_id: str,
    timestamp: str,
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
            _clean(order_no),
            _clean(contract_id),
            _clean(file_sha256).lower(),
        ]
    )
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, _clean(signature).lower()):
        raise HTTPException(status_code=401, detail="合同推送签名校验失败")


def _ensure_order_contract_returns_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS order_contract_returns (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `order_no` VARCHAR(100) NOT NULL,
                `contract_id` VARCHAR(255) NOT NULL,
                `contract_no` VARCHAR(100) DEFAULT '',
                `customer` VARCHAR(200) DEFAULT '',
                `file_name` VARCHAR(255) NOT NULL,
                `file_hash` CHAR(64) DEFAULT '',
                `uploader` VARCHAR(100) DEFAULT '',
                `uploaded_at` DATETIME(3) NULL,
                PRIMARY KEY (`id`),
                UNIQUE KEY `uq_order_contract_return_order` (`order_no`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))


def _find_order_contract(order_no: str) -> dict | None:
    """按订单找机台，返回订单总合同槽：合同号优先，无则占用订单号（与 V8 页面一致）。"""
    order_no = _clean(order_no)
    if not order_no:
        return None
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT `流水号` AS serial_no, `机型` AS model, `客户` AS customer, "
                "`占用订单号` AS order_no, `合同号` AS contract_no, `状态` AS status, `Location_Code` AS location "
                "FROM finished_goods_data WHERE TRIM(COALESCE(`占用订单号`, '')) = :order_no"
            ),
            {"order_no": order_no},
        ).mappings().all()
    if not rows:
        return None
    contract_no = ""
    customer = ""
    for row in rows:
        contract_no = contract_no or _clean(row.get("contract_no"))
        customer = customer or _clean(row.get("customer"))
    dongguan = any(
        "东莞" in _clean(r.get("customer")) or _clean(r.get("location")).upper() in {"DG-WH", "DONGGUAN", "东莞仓库"}
        for r in rows
    )
    return {
        "order_no": order_no,
        "contract_key": contract_no or order_no,
        "contract_no": contract_no,
        "customer": customer,
        "serials": [_clean(r.get("serial_no")) for r in rows if _clean(r.get("serial_no"))],
        "dongguan": dongguan,
    }


def _previous_order_contract_return(order_no: str) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT file_name, contract_id FROM order_contract_returns WHERE order_no=:order_no LIMIT 1"),
            {"order_no": order_no},
        ).mappings().first()
    return dict(row) if row else None


def _save_order_contract_return(*, order_no: str, contract_id: str, contract_no: str, customer: str,
                                file_name: str, file_hash: str, uploader: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO order_contract_returns
                    (`order_no`, `contract_id`, `contract_no`, `customer`, `file_name`, `file_hash`, `uploader`, `uploaded_at`)
                VALUES (:order_no, :contract_id, :contract_no, :customer, :file_name, :file_hash, :uploader, :uploaded_at)
                ON DUPLICATE KEY UPDATE
                    contract_id=VALUES(contract_id), contract_no=VALUES(contract_no), customer=VALUES(customer),
                    file_name=VALUES(file_name), file_hash=VALUES(file_hash), uploader=VALUES(uploader),
                    uploaded_at=VALUES(uploaded_at)
            """),
            {
                "order_no": order_no,
                "contract_id": contract_id,
                "contract_no": contract_no,
                "customer": customer,
                "file_name": file_name,
                "file_hash": file_hash,
                "uploader": uploader,
                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )


@router.post("/customer-order-contracts")
async def push_customer_order_contract(
    order_no: str = Form(...),
    contract_id: str = Form(""),
    contract_no: str = Form(""),
    customer_name: str = Form(""),
    uploader_name: str = Form("售后小程序-回传合同"),
    file: UploadFile = File(...),
    x_v8_sync_key_id: str = Header("", alias="X-V8-Sync-Key-Id"),
    x_v8_sync_timestamp: str = Header("", alias="X-V8-Sync-Timestamp"),
    x_v8_sync_signature: str = Header("", alias="X-V8-Sync-Signature"),
):
    """接收订单级「东莞回传订货合同」：一订单一合同，挂订单总合同槽。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="合同文件不能为空")
    if len(content) > MAX_CONTRACT_BYTES:
        raise HTTPException(status_code=413, detail="合同文件不能超过 10 MB")
    file_name = _clean(file.filename)
    if not file_name:
        raise HTTPException(status_code=400, detail="合同文件名不能为空")
    file_sha256 = _contract_sha256(content)

    _verify_order_signature(
        key_id=x_v8_sync_key_id,
        timestamp=x_v8_sync_timestamp,
        order_no=order_no,
        contract_id=contract_id,
        file_sha256=file_sha256,
        signature=x_v8_sync_signature,
    )

    order = _find_order_contract(order_no)
    if not order:
        raise HTTPException(status_code=404, detail="V8 未找到该订单的成品机台")
    if not order["dongguan"]:
        raise HTTPException(status_code=422, detail="该订单不是东莞客户订单，不能按东莞回传合同归档")
    resolved_contract_id = order["contract_key"]
    if _clean(contract_id) and _clean(contract_id) != resolved_contract_id:
        raise HTTPException(status_code=409, detail="推送的合同槽与 V8 订单当前合同号不一致")
    customer = _clean(customer_name) or order["customer"] or order["order_no"]

    _ensure_order_contract_returns_table()
    previous = _previous_order_contract_return(order["order_no"])
    if previous and _clean(previous.get("file_name")) and _clean(previous.get("file_name")) != file_name:
        # 一订单一合同：替换时删除旧的回传文件记录（同一合同槽下的工厂/生成合同不受影响）。
        delete_contract_file(resolved_contract_id, _clean(previous.get("file_name")), operator="售后小程序-回传合同")

    await file.seek(0)
    ok, message = await asyncio.to_thread(
        save_contract_file,
        file,
        customer,
        resolved_contract_id,
        _clean(uploader_name) or "售后小程序-回传合同",
        True,
    )
    if not ok:
        raise HTTPException(status_code=422, detail=message)

    _save_order_contract_return(
        order_no=order["order_no"],
        contract_id=resolved_contract_id,
        contract_no=_clean(contract_no) or order["contract_no"],
        customer=customer,
        file_name=file_name,
        file_hash=file_sha256,
        uploader=_clean(uploader_name) or "售后小程序-回传合同",
    )
    return {
        "ok": True,
        "orderNo": order["order_no"],
        "contractId": resolved_contract_id,
        "fileName": file_name,
        "customer": customer,
        "machineCount": len(order["serials"]),
        "message": message,
    }


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
