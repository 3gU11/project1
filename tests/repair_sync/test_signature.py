import hashlib
import unittest

from repair_sync.signer import canonical_string, sign_request


class SignatureTests(unittest.TestCase):
    def test_signature_headers_follow_contract(self):
        signed = sign_request(
            method="POST", request_path="/api/integrations/v8/snapshots", body=b"{}",
            client_id="client", key_id="key", secret="secret", idempotency_key="event-1",
            timestamp=1784140212, nonce="nonce",
        )
        self.assertEqual(signed.headers["X-V8-Content-SHA256"], hashlib.sha256(b"{}").hexdigest())
        self.assertTrue(canonical_string(
            "POST", "/api/integrations/v8/snapshots", "client", "key",
            "1784140212", "nonce", "event-1", signed.headers["X-V8-Content-SHA256"],
        ).startswith("POST\n"))
        self.assertTrue(signed.headers["X-V8-Signature"])


if __name__ == "__main__":
    unittest.main()
