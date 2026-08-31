from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import RepairSyncConfig, get_config
from .signer import sign_request

logger = logging.getLogger(__name__)
MAX_UNCOMPRESSED_SNAPSHOT_BYTES = 8 * 1024 * 1024


class SyncDisabledError(RuntimeError):
    pass


class NonRetryableSyncError(RuntimeError):
    retryable = False


class SyncConfigurationError(NonRetryableSyncError):
    pass


def _json_bytes(payload: dict[str, Any]) -> bytes:
    public_payload = {
        key: value for key, value in payload.items() if key not in {"payloadSha256", "sourceWatermark"}
    }
    return json.dumps(public_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_config(config: RepairSyncConfig) -> None:
    if not config.enabled:
        raise SyncDisabledError("repair snapshot upload is disabled (REPAIR_SYNC_ENABLED=false)")
    if not config.base_url:
        raise SyncConfigurationError("REPAIR_SYNC_BASE_URL is not configured")
    parsed = urlparse(config.base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise SyncConfigurationError("REPAIR_SYNC_BASE_URL must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SyncConfigurationError("repair sync only permits HTTPS outside localhost")
    if not config.client_id or not config.key_id or not config.hmac_secret:
        raise SyncConfigurationError("repair sync client_id, key_id and HMAC secret are required")


def upload_snapshot(
    payload: dict[str, Any],
    *,
    idempotency_key: str,
    config: RepairSyncConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    _validate_config(config)
    raw = _json_bytes(payload)
    if len(raw) > MAX_UNCOMPRESSED_SNAPSHOT_BYTES:
        raise SyncConfigurationError("uncompressed snapshot body exceeds the 8 MB first-version limit")
    body = gzip.compress(raw)
    max_body = config.max_body_mb * 1024 * 1024
    if len(body) > max_body:
        raise SyncConfigurationError(
            f"compressed snapshot body exceeds REPAIR_SYNC_MAX_BODY_MB ({config.max_body_mb} MB)"
        )
    path = config.snapshot_path if config.snapshot_path.startswith("/") else f"/{config.snapshot_path}"
    signed = sign_request(
        method="POST",
        request_path=path,
        body=body,
        client_id=config.client_id,
        key_id=config.key_id,
        secret=config.hmac_secret,
        idempotency_key=idempotency_key,
    )
    headers = dict(signed.headers)
    started = time.monotonic()
    verify: str | bool = config.ca_bundle or True
    cert: tuple[str, str] | None = None
    if config.mtls_cert and config.mtls_key:
        cert = (config.mtls_cert, config.mtls_key)
    url = f"{config.base_url.rstrip('/')}{path}"
    try:
        with httpx.Client(
            timeout=httpx.Timeout(90.0, connect=10.0, read=60.0, write=60.0),
            trust_env=False,
            follow_redirects=False,
            verify=verify,
            cert=cert,
        ) as client:
            response = client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"repair snapshot network error: {type(exc).__name__}") from exc
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if response.status_code == 409:
        try:
            conflict = response.json()
        except ValueError:
            conflict = {}
        remote_sha = str(conflict.get("payloadSha256") or conflict.get("payload_sha256") or "")
        if remote_sha and remote_sha == hashlib.sha256(raw).hexdigest():
            return {"status_code": response.status_code, "response": conflict, "idempotent_replay": True}
        raise NonRetryableSyncError("repair snapshot conflict: HTTP 409")
    if response.status_code in {401, 403, 422}:
        raise NonRetryableSyncError(f"repair snapshot non-retryable response: HTTP {response.status_code}")
    if not 200 <= response.status_code < 300:
        category = "client_error" if response.status_code < 500 else "server_error"
        raise RuntimeError(f"repair snapshot upload {category}: HTTP {response.status_code}")
    logger.info(
        "repair snapshot uploaded snapshot_id=%s sha256=%s status=%s elapsed_ms=%s",
        payload.get("snapshotId"),
        hashlib.sha256(raw).hexdigest(),
        response.status_code,
        elapsed_ms,
    )
    try:
        response_data = response.json()
    except ValueError:
        response_data = {}
    return {"status_code": response.status_code, "response": response_data}


def verify_config(config: RepairSyncConfig | None = None) -> dict[str, Any]:
    config = config or get_config()
    result = {
        "enabled": config.enabled,
        "base_url_configured": bool(config.base_url),
        "client_id_configured": bool(config.client_id),
        "key_id_configured": bool(config.key_id),
        "hmac_secret_configured": bool(config.hmac_secret),
        "mtls_configured": bool(config.mtls_cert and config.mtls_key),
        "upload_ready": False,
    }
    try:
        _validate_config(config)
    except (SyncDisabledError, SyncConfigurationError) as exc:
        result["error"] = str(exc)
    else:
        result["upload_ready"] = True
    return result
