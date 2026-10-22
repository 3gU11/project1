from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Mapping


def signature_message(
    timestamp: str,
    nonce: str,
    method: str,
    path: str,
    body: bytes,
    idempotency_key: str = "",
) -> bytes:
    body_sha256 = hashlib.sha256(body).hexdigest()
    return "\n".join((timestamp, nonce, method.upper(), path, idempotency_key, body_sha256)).encode("utf-8")


def signed_headers(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
    idempotency_key: str = "",
) -> dict[str, str]:
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("V8_SYNC_SECRET must be at least 32 bytes")
    timestamp_text = str(timestamp if timestamp is not None else int(time.time()))
    nonce_text = nonce or str(uuid.uuid4())
    signature = hmac.new(
        secret.encode("utf-8"),
        signature_message(timestamp_text, nonce_text, method, path, body, idempotency_key),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-V8-Timestamp": timestamp_text,
        "X-V8-Nonce": nonce_text,
        "X-V8-Signature": f"sha256={signature}",
    }


def canonical_json(value: object) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def snapshot_content_id(rows: list[dict], models: list[dict]) -> str:
    content = canonical_json({"models": models, "rows": rows})
    return hashlib.sha256(content).hexdigest()
