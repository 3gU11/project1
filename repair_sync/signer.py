from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SignedRequest:
    headers: dict[str, str]
    body: bytes


def content_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_string(
    method: str,
    request_path: str,
    client_id: str,
    key_id: str,
    timestamp: str,
    nonce: str,
    idempotency_key: str,
    body_digest: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            request_path,
            client_id,
            key_id,
            timestamp,
            nonce,
            idempotency_key,
            body_digest,
        ]
    )


def sign_request(
    *,
    method: str,
    request_path: str,
    body: bytes,
    client_id: str,
    key_id: str,
    secret: str,
    idempotency_key: str,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> SignedRequest:
    if not secret:
        raise ValueError("REPAIR_SYNC_HMAC_SECRET is not configured")
    timestamp_text = str(int(time.time() if timestamp is None else timestamp))
    nonce_text = nonce or secrets.token_hex(16)
    digest = content_sha256(body)
    canonical = canonical_string(
        method,
        request_path,
        client_id,
        key_id,
        timestamp_text,
        nonce_text,
        idempotency_key,
        digest,
    )
    signature = base64.b64encode(
        hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    return SignedRequest(
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "X-V8-Client-Id": client_id,
            "X-V8-Key-Id": key_id,
            "X-V8-Timestamp": timestamp_text,
            "X-V8-Nonce": nonce_text,
            "X-V8-Content-SHA256": digest,
            "Idempotency-Key": idempotency_key,
            "X-V8-Signature": signature,
        },
        body=body,
    )
