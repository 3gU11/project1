"""V8 内部接口：小程序上传合同（单机出货合同 + 交付信息上传待处理）。"""

from __future__ import annotations

import hashlib
import hmac
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import customer_contracts


def _signature(key_id: str, timestamp: int, serial_no: str, order_no: str, contract_id: str, content: bytes) -> str:
    file_sha = hashlib.sha256(content).hexdigest()
    message = "\n".join([key_id, str(timestamp), serial_no, order_no, contract_id, file_sha])
    return hmac.new(b"test-contract-secret", message.encode("utf-8"), hashlib.sha256).hexdigest()


def _delivery_signature(key_id: str, timestamp: int, client_upload_id: str, content: bytes) -> str:
    file_sha = hashlib.sha256(content).hexdigest()
    message = "\n".join([key_id, str(timestamp), client_upload_id, file_sha])
    return hmac.new(b"test-contract-secret", message.encode("utf-8"), hashlib.sha256).hexdigest()


class CustomerContractPushTests(unittest.TestCase):
    KEY_ID = "test-key-id"
    SECRET = "test-contract-secret"

    def setUp(self):
        app = FastAPI()
        app.include_router(customer_contracts.router, prefix="/api/v8")
        self.client = TestClient(app)
        self._patches = [
            patch.object(customer_contracts, "_signing_secret", return_value=self.SECRET),
            patch.object(customer_contracts, "_expected_key_id", return_value=self.KEY_ID),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self.client.close()

    def _machine(self, **overrides):
        machine = {
            "serial_no": "93-01-001",
            "model": "FR-400XS(PRO)",
            "customer": "东莞市锦宏精密五金制造有限公司",
            "order_no": "SO-2026-0001",
            "contract_no": "HT-001",
            "status": "库存中",
        }
        machine.update(overrides)
        return machine

    def _post(self, *, content=b"%PDF-1.4 contract", serial_no="93-01-001", order_no="", contract_id="", signature=None, timestamp=None):
        ts = int(time.time()) if timestamp is None else timestamp
        sig = signature if signature is not None else _signature(self.KEY_ID, ts, serial_no, order_no, contract_id, content)
        return self.client.post(
            "/api/v8/customer-contracts",
            data={
                "serial_no": serial_no,
                "order_no": order_no,
                "customer_name": "东莞市锦宏精密五金制造有限公司",
                "uploader_name": "售后小程序",
                "accepted_at": "2026-11-10",
                "contract_id": contract_id,
            },
            files={"file": ("锦宏下单表.pdf", content, "application/pdf")},
            headers={
                "X-V8-Sync-Key-Id": self.KEY_ID,
                "X-V8-Sync-Timestamp": str(ts),
                "X-V8-Sync-Signature": sig,
            },
        )

    def test_push_saves_contract_under_machine_shipping_contract_id(self):
        with (
            patch.object(customer_contracts, "_find_customer_machine", return_value=self._machine()),
            patch.object(customer_contracts, "_existing_contract_file", return_value=None),
            patch.object(customer_contracts, "save_contract_file", return_value=(True, "上传成功")) as save_mock,
        ):
            response = self._post()

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual("DG-SHIPPING-SO-2026-0001-93-01-001", body["contractId"])
        args = save_mock.call_args.args
        self.assertEqual("DG-SHIPPING-SO-2026-0001-93-01-001", args[2])

    def test_duplicate_file_is_idempotent_and_skips_save(self):
        with (
            patch.object(customer_contracts, "_find_customer_machine", return_value=self._machine()),
            patch.object(
                customer_contracts,
                "_existing_contract_file",
                return_value={"file_name": "锦宏下单表.pdf", "uploader": "售后小程序", "upload_time": "2026-11-10 10:00:00"},
            ),
            patch.object(customer_contracts, "save_contract_file") as save_mock,
        ):
            response = self._post()

        self.assertEqual(200, response.status_code, response.text)
        self.assertTrue(response.json()["duplicate"])
        save_mock.assert_not_called()

    def test_rejects_bad_signature(self):
        with patch.object(customer_contracts, "_find_customer_machine", return_value=self._machine()):
            response = self._post(signature="0" * 64)
        self.assertEqual(401, response.status_code)

    def test_rejects_expired_timestamp(self):
        with patch.object(customer_contracts, "_find_customer_machine", return_value=self._machine()):
            response = self._post(timestamp=int(time.time()) - 3600)
        self.assertEqual(401, response.status_code)

    def test_rejects_machine_without_order(self):
        with (
            patch.object(customer_contracts, "_find_customer_machine", return_value=self._machine(order_no="")),
            patch.object(customer_contracts, "save_contract_file"),
        ):
            response = self._post()
        self.assertEqual(409, response.status_code)

    def test_rejects_unknown_machine(self):
        with patch.object(customer_contracts, "_find_customer_machine", return_value=None):
            response = self._post()
        self.assertEqual(404, response.status_code)

    # === 交付信息上传（待处理）：不绑定订单/机台 ===

    def _post_delivery(self, *, client_upload_id="DI-1", content=b"%PDF-1.4 delivery info",
                       signature=None, timestamp=None):
        ts = int(time.time()) if timestamp is None else timestamp
        sig = signature if signature is not None else _delivery_signature(
            self.KEY_ID, ts, client_upload_id, content)
        return self.client.post(
            "/api/v8/delivery-info-uploads",
            data={
                "client_upload_id": client_upload_id,
                "customer_name": "东莞市锦宏精密五金制造有限公司",
                "contract_no": "HT-001",
                "uploader_name": "售后小程序-交付信息上传",
            },
            files={"file": ("锦宏下单表.pdf", content, "application/pdf")},
            headers={
                "X-V8-Sync-Key-Id": self.KEY_ID,
                "X-V8-Sync-Timestamp": str(ts),
                "X-V8-Sync-Signature": sig,
            },
        )

    def test_delivery_info_upload_enters_pending_queue_without_order(self):
        with patch.object(
            customer_contracts,
            "store_pending_delivery_info",
            return_value={"uploadId": "88", "fileName": "锦宏下单表.pdf", "status": "pending"},
        ) as store_mock:
            response = self._post_delivery()

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("88", body["uploadId"])
        self.assertEqual("pending", body["status"])
        kwargs = store_mock.call_args.kwargs
        self.assertEqual("DI-1", kwargs["client_upload_id"])
        self.assertNotIn("order_no", kwargs)
        self.assertNotIn("serial_no", kwargs)

    def test_delivery_info_upload_rejects_bad_signature(self):
        with patch.object(customer_contracts, "store_pending_delivery_info") as store_mock:
            response = self._post_delivery(signature="0" * 64)
        self.assertEqual(401, response.status_code)
        store_mock.assert_not_called()

    def test_delivery_info_upload_rejects_expired_timestamp(self):
        with patch.object(customer_contracts, "store_pending_delivery_info"):
            response = self._post_delivery(timestamp=int(time.time()) - 3600)
        self.assertEqual(401, response.status_code)

    def test_delivery_info_upload_rejects_wrong_key_id(self):
        with patch.object(customer_contracts, "store_pending_delivery_info"):
            response = self.client.post(
                "/api/v8/delivery-info-uploads",
                data={"client_upload_id": "DI-1"},
                files={"file": ("合同.pdf", b"%PDF-1.4", "application/pdf")},
                headers={
                    "X-V8-Sync-Key-Id": "wrong-key",
                    "X-V8-Sync-Timestamp": str(int(time.time())),
                    "X-V8-Sync-Signature": "0" * 64,
                },
            )
        self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
