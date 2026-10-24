"""云端合同附件回传本地（工厂 V8）。

流程：
1. V8 拉单 worker 拿到云端订单后，按订单调用 `/api/v7/dealer-orders/{orderNo}/attachments`
   获取附件元数据（文件名、MIME、大小、sha256）；
2. 逐个下载二进制附件，校验大小与 sha256；
3. 按现有合同附件规范落盘 `data/<合同号或订单号>/<原文件名>`，并写入 `contract_records`；
4. 用 `cloud_order_attachment_sync` 保证幂等，`cloud_order_attachment_scan` 避免重复扫描未变更订单。

云端附件只通过带 `X-V7-API-KEY` 的机器接口提供，不暴露对象存储路径；本地永远以内网/HTTPS 拉取为准。
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from sqlalchemy import text

from config import BASE_DIR
from database import get_engine

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ATTACHMENT_LIST_PATH = "/api/v7/dealer-orders/{order_no}/attachments"
ATTACHMENT_DOWNLOAD_PATH = "/api/v7/dealer-orders/{order_no}/attachments/{attachment_id}"


def _clean(value) -> str:
    return str(value).strip() if value is not None else ""


def _read_dotenv_value(key: str) -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _cloud_config() -> tuple[str, str]:
    base_url = (os.getenv("WECHAT_CLOUD_API_BASE") or _read_dotenv_value("WECHAT_CLOUD_API_BASE")).strip().rstrip("/")
    api_key = (os.getenv("V7_API_KEY") or _read_dotenv_value("V7_API_KEY")).strip()
    if not base_url:
        raise ValueError("WECHAT_CLOUD_API_BASE is not configured")
    if not api_key:
        raise ValueError("V7_API_KEY is required to pull order attachments")
    return base_url, api_key


def _safe_component(value: object) -> str:
    return re.sub(r'[\\/*?:"<>|\r\n]', "", _clean(value)).strip()


def _safe_file_name(value: object, fallback: str) -> str:
    raw = str(value or "").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f]", "", name).strip()
    return name or fallback


def fetch_cloud_attachments(order_no: str) -> list[dict]:
    """Return attachment metadata rows for one cloud order."""
    base_url, api_key = _cloud_config()
    path = ATTACHMENT_LIST_PATH.format(order_no=quote(_clean(order_no), safe=""))
    with httpx.Client(timeout=30.0, trust_env=False) as client:
        response = client.get(f"{base_url}{path}", headers={"X-V7-API-KEY": api_key})
    if response.status_code == 404:
        return []
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else []
    return [row for row in data or [] if isinstance(row, dict)]


def download_cloud_attachment(order_no: str, attachment_id: str) -> tuple[bytes, dict]:
    base_url, api_key = _cloud_config()
    path = ATTACHMENT_DOWNLOAD_PATH.format(
        order_no=quote(_clean(order_no), safe=""),
        attachment_id=quote(_clean(attachment_id), safe=""),
    )
    with httpx.Client(timeout=60.0, trust_env=False, follow_redirects=False) as client:
        response = client.get(f"{base_url}{path}", headers={"X-V7-API-KEY": api_key})
    response.raise_for_status()
    return response.content, dict(response.headers)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_schema(conn) -> None:
    dialect = conn.dialect.name
    suffix = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if dialect != "sqlite" else ""
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS cloud_order_attachment_sync ("
        "attachment_id VARCHAR(64) NOT NULL PRIMARY KEY,"
        "order_no VARCHAR(64) NOT NULL,"
        "contract_id VARCHAR(128) DEFAULT '',"
        "file_name VARCHAR(255) DEFAULT '',"
        "file_path VARCHAR(512) DEFAULT '',"
        "sha256 VARCHAR(64) DEFAULT '',"
        "state VARCHAR(32) NOT NULL DEFAULT 'pending',"
        "last_error VARCHAR(1000) NULL,"
        "synced_at DATETIME NULL,"
        "updated_at DATETIME NULL"
        f"){suffix}"
    ))
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS cloud_order_attachment_scan ("
        "order_no VARCHAR(64) NOT NULL PRIMARY KEY,"
        "order_updated_at VARCHAR(64) DEFAULT '',"
        "attachment_count INT DEFAULT 0,"
        "checked_at DATETIME NULL"
        f"){suffix}"
    ))
    if dialect != "sqlite":
        try:
            conn.execute(text(
                "CREATE INDEX idx_cloud_attachment_sync_order ON cloud_order_attachment_sync (order_no)"
            ))
        except Exception:
            pass


def _lookup_order(conn, order_no: str) -> dict:
    row = conn.execute(
        text(
            "SELECT order_no, contract_no, customer_name FROM dealer_orders "
            "WHERE order_no = :order_no ORDER BY line_no LIMIT 1"
        ),
        {"order_no": order_no},
    ).mappings().first()
    return dict(row) if row else {}


def _already_synced(conn, attachment_id: str) -> dict | None:
    row = conn.execute(
        text(
            "SELECT attachment_id, state, file_path, sha256 FROM cloud_order_attachment_sync "
            "WHERE attachment_id = :attachment_id"
        ),
        {"attachment_id": attachment_id},
    ).mappings().first()
    return dict(row) if row else None


def _contract_record_exists(conn, contract_id: str, file_path: str) -> bool:
    row = conn.execute(
        text(
            "SELECT id FROM contract_records WHERE contract_id = :contract_id "
            "AND file_path = :file_path LIMIT 1"
        ),
        {"contract_id": contract_id, "file_path": file_path},
    ).first()
    return row is not None


def _insert_contract_record(conn, contract_id: str, customer: str, file_name: str,
                            file_path: str, sha256: str, uploader: str, upload_time: datetime) -> None:
    if _contract_record_exists(conn, contract_id, file_path):
        return
    conn.execute(
        text(
            "INSERT INTO contract_records "
            "(contract_id, customer, file_name, file_path, file_hash, uploader, upload_time) "
            "VALUES (:contract_id, :customer, :file_name, :file_path, :file_hash, :uploader, :upload_time)"
        ),
        {
            "contract_id": contract_id,
            "customer": customer,
            "file_name": file_name,
            "file_path": file_path,
            "file_hash": sha256,
            "uploader": uploader,
            "upload_time": upload_time,
        },
    )


def _upsert_sync_row(conn, attachment_id: str, order_no: str, contract_id: str,
                     file_name: str, file_path: str, sha256: str, state: str,
                     last_error: str = "", synced_at: datetime | None = None) -> None:
    now = datetime.now()
    existing = _already_synced(conn, attachment_id)
    params = {
        "attachment_id": attachment_id,
        "order_no": order_no,
        "contract_id": contract_id,
        "file_name": file_name,
        "file_path": file_path,
        "sha256": sha256,
        "state": state,
        "last_error": last_error[:1000],
        "synced_at": synced_at,
        "updated_at": now,
    }
    if existing:
        conn.execute(
            text(
                "UPDATE cloud_order_attachment_sync SET order_no=:order_no, contract_id=:contract_id, "
                "file_name=:file_name, file_path=:file_path, sha256=:sha256, state=:state, "
                "last_error=:last_error, synced_at=COALESCE(:synced_at, synced_at), updated_at=:updated_at "
                "WHERE attachment_id=:attachment_id"
            ),
            params,
        )
        return
    conn.execute(
        text(
            "INSERT INTO cloud_order_attachment_sync "
            "(attachment_id, order_no, contract_id, file_name, file_path, sha256, state, last_error, synced_at, updated_at) "
            "VALUES (:attachment_id, :order_no, :contract_id, :file_name, :file_path, :sha256, :state, :last_error, :synced_at, :updated_at)"
        ),
        params,
    )


def _scan_unchanged(conn, order_no: str, order_updated_at: str) -> bool:
    if not _clean(order_updated_at):
        return False
    row = conn.execute(
        text("SELECT order_updated_at FROM cloud_order_attachment_scan WHERE order_no = :order_no"),
        {"order_no": order_no},
    ).first()
    return bool(row and _clean(row[0]) == _clean(order_updated_at))


def _mark_scanned(conn, order_no: str, order_updated_at: str, count: int) -> None:
    now = datetime.now()
    updated = conn.execute(
        text(
            "UPDATE cloud_order_attachment_scan SET order_updated_at=:updated, attachment_count=:count, "
            "checked_at=:checked WHERE order_no=:order_no"
        ),
        {"updated": _clean(order_updated_at), "count": count, "checked": now, "order_no": order_no},
    ).rowcount
    if updated:
        return
    conn.execute(
        text(
            "INSERT INTO cloud_order_attachment_scan (order_no, order_updated_at, attachment_count, checked_at) "
            "VALUES (:order_no, :updated, :count, :checked)"
        ),
        {"order_no": order_no, "updated": _clean(order_updated_at), "count": count, "checked": now},
    )


def _target_file(conn, order_no: str, attachment: dict) -> tuple[str, str, Path, str]:
    order = _lookup_order(conn, order_no)
    contract_id = _safe_component(order.get("contract_no")) or order_no
    customer = _clean(order.get("customer_name"))
    file_name = _safe_file_name(attachment.get("fileName"), f"{_clean(attachment.get('id'))}.bin")
    relative = Path("data") / contract_id / file_name
    return contract_id, customer, Path(BASE_DIR) / relative, str(relative).replace("\\", "/")


def _make_room_for_duplicate(path: Path, attachment_id: str, sha256: str) -> Path:
    """Keep both files when two different cloud attachments share a display name."""
    if not path.exists():
        return path
    if _sha256_file(path) == sha256:
        return path
    stem, suffix = path.stem, path.suffix
    return path.with_name(f"{stem}_{attachment_id[:8]}{suffix}")


def _sync_one_attachment(conn, order_no: str, attachment: dict) -> str:
    """Returns synced/skipped/failed state for one attachment."""
    attachment_id = _clean(attachment.get("id"))
    if not attachment_id:
        return "failed"
    existing = _already_synced(conn, attachment_id)
    if existing and existing.get("state") == "synced" and _clean(existing.get("file_path")):
        local = Path(BASE_DIR) / str(existing["file_path"])
        expected = _clean(existing.get("sha256"))
        if local.exists() and (not expected or _sha256_file(local) == expected):
            return "skipped"

    content, headers = download_cloud_attachment(order_no, attachment_id)
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise ValueError("附件超过 10 MB 限制")
    expected_size = int(attachment.get("size") or 0)
    if expected_size and len(content) != expected_size:
        raise ValueError("附件大小与云端记录不一致")
    sha256 = _sha256(content)
    expected_sha = _clean(attachment.get("sha256") or headers.get("X-Attachment-Sha256") or headers.get("x-attachment-sha256")).lower()
    if expected_sha and sha256 != expected_sha:
        raise ValueError("附件 sha256 校验失败")

    contract_id, customer, target, relative = _target_file(conn, order_no, attachment)
    target = _make_room_for_duplicate(target, attachment_id, sha256)
    relative = str(target.relative_to(Path(BASE_DIR))).replace("\\", "/")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    temp.write_bytes(content)
    os.replace(temp, target)

    _insert_contract_record(
        conn,
        contract_id=contract_id,
        customer=customer,
        file_name=target.name,
        file_path=relative,
        sha256=sha256,
        uploader="云端附件",
        upload_time=datetime.now(),
    )
    _upsert_sync_row(
        conn, attachment_id, order_no, contract_id, target.name, relative, sha256,
        state="synced", synced_at=datetime.now(),
    )
    return "synced"


def sync_cloud_order_attachments(orders: list[dict]) -> dict:
    """Download attachments for the pulled cloud orders. Never raises for one failed file."""
    unique: dict[str, str] = {}
    for order in orders or []:
        order_no = _clean((order or {}).get("order_no") or (order or {}).get("orderNo"))
        if order_no:
            unique[order_no] = _clean((order or {}).get("updated_at") or (order or {}).get("updatedAt"))

    summary = {"orders": 0, "scanned": 0, "synced": 0, "skipped": 0, "failed": 0, "errors": []}
    if not unique:
        return summary

    engine = get_engine()
    with engine.begin() as conn:
        ensure_schema(conn)

    for order_no, order_updated_at in unique.items():
        summary["orders"] += 1
        try:
            with engine.begin() as conn:
                if _scan_unchanged(conn, order_no, order_updated_at):
                    summary["scanned"] += 1
                    continue
                attachments = fetch_cloud_attachments(order_no)
                for attachment in attachments:
                    try:
                        state = _sync_one_attachment(conn, order_no, attachment)
                        summary[state] += 1
                    except Exception as exc:  # one bad attachment must not block the rest
                        attachment_id = _clean(attachment.get("id"))
                        _upsert_sync_row(
                            conn, attachment_id, order_no, "", _clean(attachment.get("fileName")), "",
                            _clean(attachment.get("sha256")).lower(), state="failed", last_error=str(exc),
                        )
                        summary["failed"] += 1
                        summary["errors"].append({"order_no": order_no, "attachment_id": attachment_id, "error": str(exc)})
                        logger.warning("cloud attachment sync failed order=%s attachment=%s: %s", order_no, attachment_id, exc)
                _mark_scanned(conn, order_no, order_updated_at, len(attachments))
                summary["scanned"] += 1
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append({"order_no": order_no, "error": str(exc)})
            logger.warning("cloud attachment order scan failed order=%s: %s", order_no, exc)
    return summary


def _attachment_rows(conn, order_no: str) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT attachment_id, order_no, contract_id, file_name, file_path, sha256, state, synced_at "
            "FROM cloud_order_attachment_sync WHERE order_no = :order_no "
            "ORDER BY synced_at, attachment_id"
        ),
        {"order_no": order_no},
    ).mappings().all()
    return [dict(row) for row in rows]


def _attachment_view(row: dict) -> dict | None:
    relative = _clean(row.get("file_path"))
    file_name = _clean(row.get("file_name"))
    if not relative or not file_name:
        return None
    root = Path(BASE_DIR).resolve()
    absolute = (root / relative).resolve()
    try:
        absolute.relative_to(root)
    except ValueError:
        return None
    if not absolute.is_file():
        return None
    attachment_id = _clean(row.get("attachment_id"))
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    return {
        "id": attachment_id,
        "orderNo": _clean(row.get("order_no")),
        "contractId": _clean(row.get("contract_id")),
        "fileName": file_name,
        "mimeType": mime_type,
        "size": absolute.stat().st_size,
        "sha256": _clean(row.get("sha256")),
        "state": _clean(row.get("state")),
        "syncedAt": _clean(row.get("synced_at")),
        "downloadUrl": f"/api/v1/dealer-orders/{_clean(row.get('order_no'))}/attachments/{attachment_id}/download",
        "previewUrl": f"/api/v1/dealer-orders/{_clean(row.get('order_no'))}/attachments/{attachment_id}/preview",
    }


def list_local_order_attachments(order_no: str) -> list[dict]:
    """Local (already pulled) attachments for one dealer order."""
    order_no = _clean(order_no)
    if not order_no:
        return []
    engine = get_engine()
    with engine.begin() as conn:
        ensure_schema(conn)
        rows = _attachment_rows(conn, order_no)
    result = []
    for row in rows:
        if _clean(row.get("state")) != "synced":
            continue
        view = _attachment_view(row)
        if view:
            result.append(view)
    return result


def find_local_order_attachment(order_no: str, attachment_id: str) -> dict | None:
    """Locate one local attachment for download; returns absolute path + metadata."""
    order_no = _clean(order_no)
    attachment_id = _clean(attachment_id)
    if not order_no or not attachment_id:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        ensure_schema(conn)
        row = conn.execute(
            text(
                "SELECT attachment_id, order_no, contract_id, file_name, file_path, sha256, state, synced_at "
                "FROM cloud_order_attachment_sync WHERE order_no = :order_no AND attachment_id = :attachment_id "
                "AND state = 'synced' LIMIT 1"
            ),
            {"order_no": order_no, "attachment_id": attachment_id},
        ).mappings().first()
    if not row:
        return None
    view = _attachment_view(dict(row))
    if not view:
        return None
    view["absolutePath"] = str((Path(BASE_DIR).resolve() / _clean(row["file_path"])).resolve())
    return view
