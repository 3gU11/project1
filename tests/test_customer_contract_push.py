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


def _order_signature(key_id: str, timestamp: int, order_no: str, contract_id: str, content: bytes) -> str:
    file_sha = hashlib.sha256(content).hexdigest()
    message = "\n".join([key_id, str(timestamp), order_no, contract_id, file_sha])
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

    def _post_order(self, *, order_no="SO-DG-001", contract_id="HT-DG-001",
                    content=b"%PDF-1.4 order contract", signature=None, timestamp=None):
        ts = int(time.time()) if timestamp is None else timestamp
        sig = signature if signature is not None else _order_signature(
            self.KEY_ID, ts, order_no, contract_id, content)
        return self.client.post(
            "/api/v8/customer-order-contracts",
            data={
                "order_no": order_no,
                "contract_id": contract_id,
                "contract_no": contract_id,
                "customer_name": "东莞宏轩机械设备有限公司",
            },
            files={"file": ("锦宏下单表.pdf", content, "application/pdf")},
            headers={
                "X-V8-Sync-Key-Id": self.KEY_ID,
                "X-V8-Sync-Timestamp": str(ts),
                "X-V8-Sync-Signature": sig,
            },
        )

    def _order(self, **overrides):
        order = {
            "order_no": "SO-DG-001",
            "contract_key": "HT-DG-001",
            "contract_no": "HT-DG-001",
            "customer": "东莞宏轩机械设备有限公司",
            "serials": ["SN-DG-001", "SN-DG-002"],
            "dongguan": True,
        }
        order.update(overrides)
        return order

    def test_pushes_order_level_contract_to_order_slot(self):
        with (
            patch.object(customer_contracts, "_find_order_contract", return_value=self._order()),
            patch.object(customer_contracts, "_ensure_order_contract_returns_table"),
            patch.object(customer_contracts, "_previous_order_contract_return", return_value=None),
            patch.object(customer_contracts, "save_contract_file", return_value=(True, "上传成功")) as save_mock,
            patch.object(customer_contracts, "_save_order_contract_return") as save_return_mock,
        ):
            response = self._post_order()

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("HT-DG-001", body["contractId"])
        self.assertEqual("SO-DG-001", body["orderNo"])
        self.assertEqual(2, body["machineCount"])
        args = save_mock.call_args.args
        self.assertEqual("HT-DG-001", args[2], "回传合同应挂订单总合同槽（合同号优先）")
        self.assertIn("回传合同", args[3])
        save_return_mock.assert_called_once()

    def test_order_contract_falls_back_to_order_no_when_contract_no_blank(self):
        order = self._order(contract_key="SO-DG-001", contract_no="")
        with (
            patch.object(customer_contracts, "_find_order_contract", return_value=order),
            patch.object(customer_contracts, "_ensure_order_contract_returns_table"),
            patch.object(customer_contracts, "_previous_order_contract_return", return_value=None),
            patch.object(customer_contracts, "save_contract_file", return_value=(True, "上传成功")) as save_mock,
            patch.object(customer_contracts, "_save_order_contract_return"),
        ):
            response = self._post_order(contract_id="SO-DG-001")

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("SO-DG-001", save_mock.call_args.args[2])

    def test_order_contract_rejects_unknown_order(self):
        with patch.object(customer_contracts, "_find_order_contract", return_value=None):
            response = self._post_order()
        self.assertEqual(404, response.status_code)

    def test_order_contract_rejects_non_dongguan_order(self):
        with (
            patch.object(customer_contracts, "_find_order_contract", return_value=self._order(dongguan=False)),
            patch.object(customer_contracts, "save_contract_file"),
        ):
            response = self._post_order()
        self.assertEqual(422, response.status_code)

    def test_order_contract_rejects_wrong_contract_slot(self):
        with patch.object(customer_contracts, "_find_order_contract", return_value=self._order()):
            response = self._post_order(contract_id="DG-SHIPPING-OTHER")
        self.assertEqual(409, response.status_code)

    def test_order_contract_rejects_bad_signature(self):
        with patch.object(customer_contracts, "_find_order_contract", return_value=self._order()):
            response = self._post_order(signature="0" * 64)
        self.assertEqual(401, response.status_code)

    def test_replaces_previous_returned_file(self):
        with (
            patch.object(customer_contracts, "_find_order_contract", return_value=self._order()),
            patch.object(customer_contracts, "_ensure_order_contract_returns_table"),
            patch.object(customer_contracts, "_previous_order_contract_return",
                         return_value={"file_name": "旧回传合同.pdf", "contract_id": "HT-DG-001"}),
            patch.object(customer_contracts, "delete_contract_file") as delete_mock,
            patch.object(customer_contracts, "save_contract_file", return_value=(True, "上传成功")),
            patch.object(customer_contracts, "_save_order_contract_return"),
        ):
            response = self._post_order()
        self.assertEqual(200, response.status_code, response.text)
        delete_mock.assert_called_once()
        self.assertEqual("旧回传合同.pdf", delete_mock.call_args.args[1])


if __name__ == "__main__":
    unittest.main()

