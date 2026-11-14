"""交付信息上传（待处理）：V8 侧接收、查看、手动选择机台处理。

业务口径（2026-11-14）：
- 东莞回传合同含机台编号、购货单位名称/个人姓名与地址，上传时不绑定订单/机台；
- 先进入本模块的待处理队列（文件保存在 data/delivery-info-pending/...）；
- 上传后自动识别购货单位/地址/机台号并预填，V8 操作人员核对附件、
  手动选择机台 -> 系统把合同归档到订单总合同槽，并记录“该上传处理了哪些机台”，
  客户成品列表据此显示交付信息已上传；
- 本模块不做自动发货，出货仍走现有确认出货/订单规划流程。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from api.routes.auth import get_current_user_context, require_permissions
from config import BASE_DIR
from crud.audit_logs import append_audit_log
from crud.delivery_info_recognition import recognize_delivery_info_upload
from database import get_engine

router = APIRouter()

MAX_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
PENDING_ROOT = os.path.join(BASE_DIR, "data", "delivery-info-pending")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _safe_name(value: str, fallback: str = "contract.pdf") -> str:
    name = os.path.basename(_clean(value) or fallback)
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip()
    return name[:200] or fallback


def _safe_contract_id(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", _clean(value)).strip()[:100] or "UNKNOWN"


def ensure_delivery_info_tables() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS delivery_info_uploads (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `client_upload_id` VARCHAR(64) DEFAULT '',
                `file_name` VARCHAR(255) NOT NULL,
                `file_path` VARCHAR(512) NOT NULL,
                `file_hash` CHAR(64) DEFAULT '',
                `customer` VARCHAR(200) DEFAULT '',
                `buyer_name` VARCHAR(200) DEFAULT '',
                `buyer_address` VARCHAR(500) DEFAULT '',
                `machine_nos` TEXT,
                `contract_no` VARCHAR(100) DEFAULT '',
                `uploader` VARCHAR(100) DEFAULT '',
                `uploaded_at` DATETIME(3) NULL,
                `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
                `processed_by` VARCHAR(100) DEFAULT '',
                `processed_at` DATETIME(3) NULL,
                `processed_note` TEXT,
                PRIMARY KEY (`id`),
                KEY `idx_diu_status` (`status`),
                KEY `idx_diu_client` (`client_upload_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS delivery_info_upload_machines (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `upload_id` BIGINT NOT NULL,
                `serial_no` VARCHAR(100) NOT NULL,
                `order_no` VARCHAR(100) DEFAULT '',
                `created_at` DATETIME(3) NULL,
                PRIMARY KEY (`id`),
                UNIQUE KEY `uq_diu_machine` (`upload_id`, `serial_no`),
                KEY `idx_diu_machine_serial` (`serial_no`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
    _ensure_delivery_info_columns()


def _ensure_delivery_info_columns() -> None:
    """老库已建表时补齐回传合同有效字段（购货单位/地址/机台号）。"""
    from sqlalchemy import inspect

    engine = get_engine()
    columns = {str(col.get("name")) for col in inspect(engine).get_columns("delivery_info_uploads")}
    additions = {
        "buyer_name": "VARCHAR(200) DEFAULT ''",
        "buyer_address": "VARCHAR(500) DEFAULT ''",
        "machine_nos": "TEXT",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE delivery_info_uploads ADD COLUMN `{name}` {ddl}"))


def store_pending_delivery_info(
    *,
    client_upload_id: str,
    file_name: str,
    content: bytes,
    customer: str = "",
    buyer_name: str = "",
    buyer_address: str = "",
    machine_nos: str = "",
    contract_no: str = "",
    uploader: str = "",
) -> dict:
    """保存待处理上传文件并落库，返回 {uploadId, fileName, status}。"""
    if not content:
        raise HTTPException(status_code=400, detail="交付信息文件不能为空")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="交付信息文件不能超过 10 MB")
    safe_name = _safe_name(file_name)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="仅支持 PDF、Word、JPG、PNG")
    ensure_delivery_info_tables()
    token = uuid.uuid4().hex
    rel_dir = os.path.join("data", "delivery-info-pending", token)
    abs_dir = os.path.join(BASE_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(abs_dir, safe_name)
    with open(abs_path, "wb") as handle:
        handle.write(content)
    rel_path = os.path.join(rel_dir, safe_name)
    file_hash = hashlib.sha256(content).hexdigest()
    uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_engine().begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO delivery_info_uploads
                    (`client_upload_id`, `file_name`, `file_path`, `file_hash`, `customer`,
                     `buyer_name`, `buyer_address`, `machine_nos`, `contract_no`, `uploader`, `uploaded_at`, `status`)
                VALUES (:client_upload_id, :file_name, :file_path, :file_hash, :customer,
                        :buyer_name, :buyer_address, :machine_nos, :contract_no, :uploader, :uploaded_at, 'pending')
            """),
            {
                "client_upload_id": _clean(client_upload_id),
                "file_name": safe_name,
                "file_path": rel_path,
                "file_hash": file_hash,
                "customer": _clean(customer)[:200],
                "buyer_name": _clean(buyer_name)[:200],
                "buyer_address": _clean(buyer_address)[:500],
                "machine_nos": _clean(machine_nos)[:2000],
                "contract_no": _clean(contract_no)[:100],
                "uploader": _clean(uploader)[:100] or "售后小程序-交付信息上传",
                "uploaded_at": uploaded_at,
            },
        )
        upload_id = result.lastrowid
    return {
        "uploadId": str(upload_id),
        "fileName": safe_name,
        "status": "pending",
        # 供上传入口在保存后直接识别（不依赖再次查库）。
        "filePath": rel_path,
    }


def _upload_row(upload_id: int) -> dict:
    ensure_delivery_info_tables()
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM delivery_info_uploads WHERE id=:id LIMIT 1"),
            {"id": upload_id},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="交付信息上传记录不存在")
    return dict(row)


@router.get("/delivery-info-uploads")
def list_delivery_info_uploads(
    status: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_permissions("QUERY")),
):
    ensure_delivery_info_tables()
    clauses = []
    params: dict = {"limit": limit}
    if _clean(status):
        clauses.append("`status` = :status")
        params["status"] = _clean(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM delivery_info_uploads{where} ORDER BY `id` DESC LIMIT :limit"),
            params,
        ).mappings().all()
    return {"data": [dict(row) for row in rows], "total": len(rows)}


@router.get("/delivery-info-uploads/{upload_id}/file")
def download_delivery_info_file(
    upload_id: int,
    current_user: dict = Depends(require_permissions("QUERY")),
):
    row = _upload_row(upload_id)
    abs_path = os.path.join(BASE_DIR, _clean(row.get("file_path")))
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="交付信息附件已不存在")
    return FileResponse(abs_path, filename=_clean(row.get("file_name")))


class ProcessDeliveryInfoPayload(BaseModel):
    serial_nos: list[str] = Field(min_length=1, max_length=500)
    # 操作人员对照附件预览填写（小程序上传时不再要求填写）。
    buyer_name: str = ""
    buyer_address: str = ""
    machine_nos: str = ""


@router.post("/delivery-info-uploads/{upload_id}/process")
def process_delivery_info_upload(
    upload_id: int,
    payload: ProcessDeliveryInfoPayload,
    current_user: dict = Depends(require_permissions("SHIP_CONFIRM")),
):
    """手动选择机台处理：合同归档到订单总合同槽，并记录本次处理的机台。"""
    row = _upload_row(upload_id)
    if _clean(row.get("status")) == "processed":
        raise HTTPException(status_code=409, detail="该交付信息已处理")
    serials = sorted({_clean(sn) for sn in payload.serial_nos if _clean(sn)})
    if not serials:
        raise HTTPException(status_code=422, detail="请选择机台")
    ensure_delivery_info_tables()
    with get_engine().begin() as conn:
        machines = conn.execute(
            text("SELECT * FROM finished_goods_data WHERE `流水号` IN :sns")
            .bindparams(bindparam("sns", expanding=True)),
            {"sns": serials},
        ).mappings().all()
        if len(machines) != len(serials):
            raise HTTPException(status_code=422, detail="部分机台不存在，请刷新后重新选择")
        orders = sorted({_clean(r.get("占用订单号")) for r in machines if _clean(r.get("占用订单号"))})
        if len(orders) != 1:
            raise HTTPException(status_code=422, detail="所选机台必须属于同一个销售订单")
        order_no = orders[0]
        contract_no = ""
        for machine in machines:
            contract_no = contract_no or _clean(machine.get("合同号"))
        contract_id = _safe_contract_id(contract_no or order_no)
        customer = ""
        for machine in machines:
            customer = customer or _clean(machine.get("客户"))
        customer = customer or _clean(row.get("customer")) or order_no

        # 把待处理文件归档到订单总合同槽（data/{合同号或订单号}/），并写合同记录。
        source_abs = os.path.join(BASE_DIR, _clean(row.get("file_path")))
        if not os.path.isfile(source_abs):
            raise HTTPException(status_code=422, detail="交付信息待处理附件已不存在")
        target_dir = os.path.join(BASE_DIR, "data", contract_id)
        os.makedirs(target_dir, exist_ok=True)
        file_name = _safe_name(row.get("file_name"))
        target_abs = os.path.join(target_dir, file_name)
        shutil.copyfile(source_abs, target_abs)
        file_hash = _clean(row.get("file_hash"))
        conn.execute(
            text("""
                INSERT INTO contract_records
                    (`contract_id`, `customer`, `file_name`, `file_path`, `file_hash`, `uploader`, `upload_time`)
                VALUES (:contract_id, :customer, :file_name, :file_path, :file_hash, :uploader, :upload_time)
            """),
            {
                "contract_id": contract_id,
                "customer": customer,
                "file_name": file_name,
                "file_path": os.path.join("data", contract_id, file_name),
                "file_hash": file_hash,
                "uploader": _clean(row.get("uploader")) or "售后小程序-交付信息上传",
                "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        operator = _clean(current_user.get("name") or current_user.get("username") or "System")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(text("DELETE FROM delivery_info_upload_machines WHERE upload_id=:uid"), {"uid": upload_id})
        conn.execute(
            text("""
                INSERT INTO delivery_info_upload_machines (`upload_id`, `serial_no`, `order_no`, `created_at`)
                VALUES (:upload_id, :serial_no, :order_no, :created_at)
            """),
            [{"upload_id": upload_id, "serial_no": sn, "order_no": order_no, "created_at": now} for sn in serials],
        )
        conn.execute(
            text("""
                UPDATE delivery_info_uploads
                SET status='processed', processed_by=:operator, processed_at=:now,
                    processed_note=:note,
                    buyer_name=COALESCE(NULLIF(:buyer_name, ''), buyer_name),
                    buyer_address=COALESCE(NULLIF(:buyer_address, ''), buyer_address),
                    machine_nos=COALESCE(NULLIF(:machine_nos, ''), machine_nos)
                WHERE id=:id
            """),
            {
                "operator": operator,
                "now": now,
                "note": f"关联订单 {order_no}，机台：{', '.join(serials)}",
                "buyer_name": _clean(payload.buyer_name)[:200],
                "buyer_address": _clean(payload.buyer_address)[:500],
                "machine_nos": _clean(payload.machine_nos)[:2000],
                "id": upload_id,
            },
        )
    try:
        append_audit_log(
            module="客户成品",
            action_type="处理交付信息上传",
            biz_type="交付信息",
            content=f"上传 #{upload_id}；订单 {order_no}；机台：{', '.join(serials)}",
            user_id=_clean(current_user.get("username")),
            username=operator,
        )
    except Exception:
        pass
    return {
        "uploadId": str(upload_id),
        "status": "processed",
        "orderNo": order_no,
        "contractId": contract_id,
        "serialNos": serials,
    }


@router.post("/delivery-info-uploads/{upload_id}/recognize")
def recognize_delivery_info_upload_endpoint(
    upload_id: int,
    current_user: dict = Depends(require_permissions("QUERY")),
):
    """重新识别交付信息附件的机台号、购货单位/个人姓名与地址并回填。

    - 待处理（pending）记录：识别成功且得到值时回填（只填空值）；
    - 已处理（processed）记录：只返回识别结果，不回填（避免改动已归档合同关联）；
    - 附件缺失、OCR 未启动、PDF 损坏等只返回 warnings，不报错。
    """
    row = _upload_row(upload_id)
    try:
        recognized = recognize_delivery_info_upload(upload_id)
    except Exception as exc:  # 识别本身已容错，这里只兜底极端情况
        recognized = {
            "machine_nos": [],
            "raw_numbers": [],
            "machines": [],
            "buyer_name": "",
            "buyer_address": "",
            "method": "",
            "warnings": [f"识别失败：{exc}"],
            "machine_nos_text": "",
            "persisted": False,
        }
    buyer_name = _clean(recognized.get("buyer_name")) or _clean(row.get("buyer_name"))
    buyer_address = _clean(recognized.get("buyer_address")) or _clean(row.get("buyer_address"))
    data = {
        "uploadId": str(upload_id),
        "fileName": _clean(row.get("file_name")),
        "status": _clean(row.get("status")),
        "buyer_name": buyer_name,
        "buyerName": buyer_name,
        "buyer_address": buyer_address,
        "buyerAddress": buyer_address,
        "machine_nos": recognized.get("machine_nos") or [],
        "machineNos": _clean(recognized.get("machine_nos_text")),
        "raw_numbers": recognized.get("raw_numbers") or [],
        "machines": recognized.get("machines") or [],
        "method": _clean(recognized.get("method")),
        "warnings": recognized.get("warnings") or [],
        "persisted": bool(recognized.get("persisted")),
    }
    return {"data": data}
