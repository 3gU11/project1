"""V8 内部接口：售后小程序推送东莞出货合同（HMAC 签名）的接口测试。"""

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
        # 签名绑定的是调用方实际提交的字段（contract_id 为空时由 V8 解析并生成）。
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
        self.assertEqual("SO-2026-0001", body["orderNo"])
        self.assertEqual("93-01-001", body["serialNo"])
        args = save_mock.call_args.args
        self.assertEqual("DG-SHIPPING-SO-2026-0001-93-01-001", args[2])
        self.assertEqual("售后小程序", args[3])

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


if __name__ == "__main__":
    unittest.main()

