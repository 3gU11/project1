import hashlib
import hmac
import pytest

from crud.cloud_bridge_auth import signed_headers, snapshot_content_id


def test_signature_matches_bridge_protocol_vector():
    body = b'{"rows":[],"models":[]}'
    headers = signed_headers(
        "test-bridge-secret-32-bytes-minimum!",
        "post",
        "/api/v8/bridge/snapshot",
        body,
        timestamp=1792545600,
        nonce="12345678-1234-4234-8234-123456789abc",
    )
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"1792545600\n12345678-1234-4234-8234-123456789abc\nPOST\n/api/v8/bridge/snapshot\n\n{body_hash}".encode()
    expected = hmac.new(b"test-bridge-secret-32-bytes-minimum!", message, hashlib.sha256).hexdigest()
    assert headers["X-V8-Signature"] == f"sha256={expected}"
    assert headers["X-V8-Signature"] == "sha256=48d03954fd33628ab182cff296c29b97f53ee17bd303a1821d55ef9198efc96b"


def test_signature_covers_idempotency_key():
    body = b'{"status":"approved"}'
    headers = signed_headers(
        "test-bridge-secret-32-bytes-minimum!",
        "POST",
        "/api/dealer/orders/DO1/v8-status",
        body,
        timestamp=1792545600,
        nonce="12345678-1234-4234-8234-123456789abc",
        idempotency_key="event-1",
    )
    assert headers["X-V8-Signature"] == "sha256=e82afedb961389f027a90d96b4e475ad2a169d5dfd61802f8d5777b581be1d8c"


def test_snapshot_content_id_is_stable():
    content_id = snapshot_content_id(
        [{"model": "A", "quantity": 1}], [{"model_name": "A", "enabled": 1}]
    )
    assert content_id == snapshot_content_id(
        [{"quantity": 1, "model": "A"}], [{"enabled": 1, "model_name": "A"}]
    )
    assert content_id == "65122fc3a3886632989ac84132dcb965416ed765676e76782c701cd3a5798471"


def test_rejects_short_hmac_keys():
    with pytest.raises(ValueError, match="32 bytes"):
        signed_headers("too-short", "GET", "/api/v8/bridge/orders", b"")
