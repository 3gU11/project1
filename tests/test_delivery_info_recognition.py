"""交付信息合同附件机台号自动识别（crud/delivery_info_recognition.py）测试。

覆盖：
- 候选提取/归一化/与 V8 东莞机台流水号比对（注入假机台，不依赖数据库）；
- 带横线 ``96-08-306`` 与连写 ``9608306`` 两种写法；
- 真实文本层 PDF 提取（测试内用 pypdf 可直接读取的最小 PDF；
  OCR 服务用 monkeypatch 模拟，不要求本机 OCR 已启动）；
- 无文本层/损坏 PDF、OCR 服务失败、.doc 等异常场景只 warning 不抛错；
- 上传记录识别回填（pending 回填、processed 不回填）；
- 上传接收入口自动识别，以及识别失败不影响上传成功。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import customer_contracts, delivery_info_uploads
from config import BASE_DIR
from crud import delivery_info_recognition as recognition

FAKE_MACHINES = [
    {
        "serial_no": "96-08-306",
        "model": "FR-400XS(PRO)",
        "customer": "东莞市南城（东莞宏轩机械设备）",
        "order_no": "SO-20261007-B71B",
        "status": "已出库",
        "location_code": "C04",
    },
    {
        "serial_no": "96-09-359",
        "model": "FR-600XS(PRO)",
        "customer": "东莞市南城（东莞宏轩机械设备）",
        "order_no": "SO-20261104-E5EF",
        "status": "已出库",
        "location_code": "C10",
    },
]

CONTRACT_TEXT = (
    "1.线切割机床 瑞钧 FR-400XS(PRO) 9608306/202610 套 1 125000 125000\n"
    "联系人姓名 陈生 联系电话 13825752665\n"
    "供方电话 13925851671 电话：0512-57175508\n"
)


def _build_text_pdf(text: str) -> bytes:
    """生成 pypdf 能提取文本层的最小单页 PDF（测试内自带，不依赖外部样例）。"""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    ).encode()
    return bytes(out)


class RecognitionCandidateTests(unittest.TestCase):
    """文本候选/归一化/匹配：只命中 V8 东莞机台流水号，排除干扰数字。"""

    def test_normalize_machine_number(self):
        self.assertEqual("9608306", recognition.normalize_machine_number("96-08-306"))
        self.assertEqual("9608306", recognition.normalize_machine_number("9608306"))
        self.assertEqual("9608306", recognition.normalize_machine_number(" 96－08－306 "))

    def test_match_text_only_hits_internal_serial_no(self):
        matched = recognition.match_machine_numbers(CONTRACT_TEXT, FAKE_MACHINES)
        self.assertEqual(["96-08-306"], matched["machine_nos"])
        self.assertEqual([], matched["raw_numbers"])
        for noise in ("125000", "202610", "13825752665", "13925851671", "57175508"):
            self.assertNotIn(noise, matched["machine_nos"])
        machine = matched["machines"][0]
        self.assertEqual("FR-400XS(PRO)", machine["机型"])
        self.assertEqual("SO-20261007-B71B", machine["占用订单号"])
        self.assertEqual("C04", machine["Location_Code"])

    def test_match_hyphenated_serial_no(self):
        matched = recognition.match_machine_numbers("合同机台：96-08-306", FAKE_MACHINES)
        self.assertEqual(["96-08-306"], matched["machine_nos"])

    def test_unmatched_seven_digit_number_becomes_raw(self):
        matched = recognition.match_machine_numbers("机台 9608399 价格 125000", FAKE_MACHINES)
        self.assertEqual([], matched["machine_nos"])
        self.assertEqual(["9608399"], matched["raw_numbers"])

    def test_hyphen_form_unmatched_is_not_raw(self):
        matched = recognition.match_machine_numbers("机台 96-08-999", FAKE_MACHINES)
        self.assertEqual([], matched["machine_nos"])
        self.assertEqual([], matched["raw_numbers"])

    def test_order_and_dedup(self):
        matched = recognition.match_machine_numbers(
            "9608306 96-09-359 96-08-306", FAKE_MACHINES
        )
        self.assertEqual(["96-08-306", "96-09-359"], matched["machine_nos"])

    def test_machines_cap_is_50(self):
        machines = []
        serials = []
        for index in range(100, 160):
            serial = f"96-10-{index}"
            serials.append(serial)
            machines.append(
                {"serial_no": serial, "model": "FR-400XS(PRO)", "customer": "东莞市测试",
                 "order_no": "SO-1", "status": "已出库", "location_code": "A01"}
            )
        matched = recognition.match_machine_numbers(" ".join(serials), machines)
        self.assertEqual(50, len(matched["machine_nos"]))
        self.assertEqual(serials[:50], matched["machine_nos"])

    def test_empty_text_returns_empty_result(self):
        matched = recognition.match_machine_numbers("", FAKE_MACHINES)
        self.assertEqual([], matched["machine_nos"])
        self.assertEqual([], matched["machines"])
        self.assertEqual([], matched["raw_numbers"])


class RecognitionFileTests(unittest.TestCase):
    """PDF/图片/.doc 等文件识别路径（OCR 服务用 monkeypatch 模拟）。"""

    def setUp(self):
        data_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(prefix=".pytest-recognition-", dir=data_dir)
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _write(self, name: str, content: bytes) -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_pdf_text_layer_recognition(self):
        pdf_path = self._write("contract.pdf", _build_text_pdf("FR-400XS(PRO) 9608306/202610"))
        with patch.object(recognition, "_load_dongguan_machines", return_value=FAKE_MACHINES):
            result = recognition.recognize_delivery_info_file(pdf_path)
        self.assertEqual("pdf-text", result["method"])
        self.assertEqual(["96-08-306"], result["machine_nos"])
        self.assertIn("9608306", result["text"])
        self.assertEqual([], result["raw_numbers"])

    def test_pdf_without_loadable_text_or_images_warns_without_raising(self):
        broken = self._write("broken.pdf", b"not a real pdf")
        with patch.object(recognition, "_load_dongguan_machines", return_value=FAKE_MACHINES):
            result = recognition.recognize_delivery_info_file(broken)
        self.assertEqual([], result["machine_nos"])
        self.assertTrue(result["warnings"])

    def test_image_uses_ocr_service_and_matches_machine(self):
        image_path = self._write("contract.png", b"\x89PNG\r\n\x1a\nfake-image")
        with (
            patch.object(recognition, "_load_dongguan_machines", return_value=FAKE_MACHINES),
            patch.object(recognition, "_post_ocr", return_value="FR-400XS(PRO) 9608306/202610"),
        ):
            result = recognition.recognize_delivery_info_file(image_path)
        self.assertEqual("ocr", result["method"])
        self.assertEqual(["96-08-306"], result["machine_nos"])

    def test_ocr_failure_only_warns(self):
        image_path = self._write("contract.jpg", b"fake-jpg")
        with (
            patch.object(recognition, "_load_dongguan_machines", return_value=FAKE_MACHINES),
            patch.object(recognition, "_post_ocr", side_effect=RuntimeError("ocr service down")),
        ):
            result = recognition.recognize_delivery_info_file(image_path)
        self.assertEqual([], result["machine_nos"])
        self.assertTrue(any("OCR" in item for item in result["warnings"]))

    def test_missing_file_returns_warning(self):
        result = recognition.recognize_delivery_info_file(os.path.join(self.tmpdir, "not-exists.pdf"))
        self.assertEqual([], result["machine_nos"])
        self.assertEqual("", result["method"])
        self.assertTrue(result["warnings"])

    def test_empty_path_returns_warning(self):
        result = recognition.recognize_delivery_info_file("")
        self.assertEqual([], result["machine_nos"])
        self.assertTrue(result["warnings"])

    def test_doc_is_not_supported_but_does_not_raise(self):
        doc_path = self._write("contract.doc", b"legacy word")
        result = recognition.recognize_delivery_info_file(doc_path)
        self.assertEqual([], result["machine_nos"])
        self.assertTrue(any(".doc" in item for item in result["warnings"]))


class RecognitionUploadTests(unittest.TestCase):
    """按上传记录识别/回填：pending 回填，processed 只返回结果。"""

    def setUp(self):
        data_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(prefix=".pytest-recognition-", dir=data_dir)
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.file_path = os.path.join(self.tmpdir, "contract.pdf")
        with open(self.file_path, "wb") as handle:
            handle.write(_build_text_pdf("FR-400XS(PRO) 9608306/202610"))

    def _recognized(self, *, machine_nos=None, raw_numbers=None):
        return {
            "text": "9608306",
            "method": "pdf-text",
            "machine_nos": machine_nos if machine_nos is not None else ["96-08-306"],
            "raw_numbers": raw_numbers or [],
            "machines": [{"serial_no": "96-08-306"}] if machine_nos is None else [],
            "candidates": [],
            "warnings": [],
        }

    def test_pending_upload_persists_internal_serial_no(self):
        with (
            patch.object(recognition, "_fetch_upload_row", return_value={"status": "pending", "file_path": ""}),
            patch.object(recognition, "recognize_delivery_info_file", return_value=self._recognized()),
            patch.object(recognition, "_save_upload_machine_nos") as save_mock,
        ):
            result = recognition.recognize_delivery_info_upload(88, file_path=self.file_path)
        save_mock.assert_called_once_with(88, "96-08-306")
        self.assertTrue(result["persisted"])
        self.assertEqual("96-08-306", result["machine_nos_text"])
        self.assertEqual("pending", result["status"])

    def test_pending_upload_persists_raw_numbers_when_no_machine_matched(self):
        recognized = {
            "text": "",
            "method": "pdf-text",
            "machine_nos": [],
            "raw_numbers": ["9608399"],
            "machines": [],
            "candidates": [],
            "warnings": [],
        }
        with (
            patch.object(recognition, "_fetch_upload_row", return_value={"status": "pending", "file_path": ""}),
            patch.object(recognition, "recognize_delivery_info_file", return_value=recognized),
            patch.object(recognition, "_save_upload_machine_nos") as save_mock,
        ):
            result = recognition.recognize_delivery_info_upload(89, file_path=self.file_path)
        save_mock.assert_called_once_with(89, "9608399")
        self.assertTrue(result["persisted"])

    def test_processed_upload_does_not_persist(self):
        with (
            patch.object(recognition, "_fetch_upload_row", return_value={"status": "processed", "file_path": ""}),
            patch.object(recognition, "recognize_delivery_info_file", return_value=self._recognized()),
            patch.object(recognition, "_save_upload_machine_nos") as save_mock,
        ):
            result = recognition.recognize_delivery_info_upload(90, file_path=self.file_path)
        save_mock.assert_not_called()
        self.assertFalse(result["persisted"])
        self.assertEqual(["96-08-306"], result["machine_nos"])
        self.assertTrue(any("已处理" in item for item in result["warnings"]))

    def test_missing_upload_record_returns_warning(self):
        with patch.object(recognition, "_fetch_upload_row", return_value=None):
            result = recognition.recognize_delivery_info_upload(91)
        self.assertEqual([], result["machine_nos"])
        self.assertTrue(result["warnings"])
        self.assertFalse(result["persisted"])

    def test_absent_attachment_returns_warning(self):
        with patch.object(
            recognition,
            "_fetch_upload_row",
            return_value={"status": "pending", "file_path": "data/not-exists.pdf"},
        ):
            result = recognition.recognize_delivery_info_upload(92)
        self.assertEqual([], result["machine_nos"])
        self.assertTrue(any("不存在" in item for item in result["warnings"]))


class RecognitionRouteTests(unittest.TestCase):
    """重识别接口：直接调用路由函数，避免依赖真实登录/鉴权。"""

    def test_recognize_endpoint_payload_contract(self):
        recognized = {
            "method": "pdf-text",
            "machine_nos": ["96-08-306"],
            "raw_numbers": [],
            "machines": [{"serial_no": "96-08-306", "机型": "FR-400XS(PRO)"}],
            "warnings": [],
            "machine_nos_text": "96-08-306",
            "persisted": True,
        }
        with (
            patch.object(delivery_info_uploads, "_upload_row", return_value={"file_name": "锦宏下单表.pdf", "status": "pending"}),
            patch.object(delivery_info_uploads, "recognize_delivery_info_upload", return_value=recognized),
        ):
            payload = delivery_info_uploads.recognize_delivery_info_upload_endpoint(
                88, current_user={"username": "qa"}
            )
        data = payload["data"]
        self.assertEqual("88", data["uploadId"])
        self.assertEqual("pending", data["status"])
        self.assertEqual(["96-08-306"], data["machine_nos"])
        self.assertEqual("96-08-306", data["machineNos"])
        self.assertEqual("pdf-text", data["method"])
        self.assertTrue(data["persisted"])
        self.assertEqual("锦宏下单表.pdf", data["fileName"])

    def test_recognize_endpoint_tolerates_recognition_exception(self):
        with (
            patch.object(delivery_info_uploads, "_upload_row", return_value={"file_name": "x.pdf", "status": "pending"}),
            patch.object(
                delivery_info_uploads,
                "recognize_delivery_info_upload",
                side_effect=RuntimeError("boom"),
            ),
        ):
            payload = delivery_info_uploads.recognize_delivery_info_upload_endpoint(
                89, current_user={"username": "qa"}
            )
        self.assertEqual([], payload["data"]["machine_nos"])
        self.assertTrue(payload["data"]["warnings"])
        self.assertFalse(payload["data"]["persisted"])


class DeliveryInfoUploadAutoRecognitionTests(unittest.TestCase):
    """上传接收入口：未传 machine_nos 时自动识别并回填；识别失败不影响上传。"""

    KEY_ID = "test-key-id"
    SECRET = "test-contract-secret"

    def setUp(self):
        app = FastAPI()
        app.include_router(customer_contracts.router, prefix="/api/v8")
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self._patches = [
            patch.object(customer_contracts, "_signing_secret", return_value=self.SECRET),
            patch.object(customer_contracts, "_expected_key_id", return_value=self.KEY_ID),
        ]
        for item in self._patches:
            item.start()
            self.addCleanup(item.stop)

    def _post(self, *, client_upload_id="DI-1", machine_nos="", content=b"%PDF-1.4 delivery info"):
        timestamp = int(time.time())
        file_sha = hashlib.sha256(content).hexdigest()
        message = "\n".join([self.KEY_ID, str(timestamp), client_upload_id, file_sha])
        signature = hmac.new(b"test-contract-secret", message.encode("utf-8"), hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/v8/delivery-info-uploads",
            data={
                "client_upload_id": client_upload_id,
                "customer_name": "东莞市锦宏精密五金制造有限公司",
                "buyer_name": "东莞市锦宏精密五金制造有限公司",
                "machine_nos": machine_nos,
                "uploader_name": "售后小程序-交付信息上传",
            },
            files={"file": ("锦宏下单表.pdf", content, "application/pdf")},
            headers={
                "X-V8-Sync-Key-Id": self.KEY_ID,
                "X-V8-Sync-Timestamp": str(timestamp),
                "X-V8-Sync-Signature": signature,
            },
        )

    def _stored(self):
        return {
            "uploadId": "88",
            "fileName": "锦宏下单表.pdf",
            "status": "pending",
            "filePath": "data\\delivery-info-pending\\token\\锦宏下单表.pdf",
        }

    def _recognized(self):
        return {
            "method": "pdf-text",
            "machine_nos": ["96-08-306"],
            "raw_numbers": [],
            "machines": [{"serial_no": "96-08-306", "机型": "FR-400XS(PRO)"}],
            "warnings": [],
            "machine_nos_text": "96-08-306",
            "persisted": True,
        }

    def test_upload_auto_recognition_fills_machine_nos(self):
        with (
            patch.object(customer_contracts, "store_pending_delivery_info", return_value=self._stored()),
            patch.object(
                customer_contracts, "recognize_delivery_info_upload", return_value=self._recognized()
            ) as recognize_mock,
        ):
            response = self._post()
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("96-08-306", body["machineNos"])
        self.assertEqual(["96-08-306"], body["recognition"]["machine_nos"])
        recognize_mock.assert_called_once()
        self.assertEqual(88, recognize_mock.call_args.args[0])

    def test_upload_with_machine_nos_skips_recognition(self):
        with (
            patch.object(customer_contracts, "store_pending_delivery_info", return_value=self._stored()),
            patch.object(customer_contracts, "recognize_delivery_info_upload") as recognize_mock,
        ):
            response = self._post(machine_nos="9608306/202610")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("9608306/202610", body["machineNos"])
        self.assertIsNone(body["recognition"])
        recognize_mock.assert_not_called()

    def test_upload_succeeds_when_recognition_fails(self):
        with (
            patch.object(customer_contracts, "store_pending_delivery_info", return_value=self._stored()),
            patch.object(
                customer_contracts,
                "recognize_delivery_info_upload",
                side_effect=RuntimeError("recognition exploded"),
            ),
        ):
            response = self._post()
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("", body["machineNos"])
        self.assertTrue(body["recognition"]["warnings"])


if __name__ == "__main__":
    unittest.main()
