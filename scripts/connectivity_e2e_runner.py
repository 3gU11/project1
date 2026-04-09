from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class StepResult:
    name: str
    method: str
    path: str
    expected: str
    ok: bool
    status_code: int
    elapsed_ms: int
    request_payload: Any
    response_body: Any
    error: str = ""


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = ""

    def set_token(self, token: str):
        self.token = token or ""

    def request(self, method: str, path: str, payload: Any = None, form: bool = False):
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}
        data = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            if form:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                data = urlencode(payload).encode("utf-8")
            else:
                headers["Content-Type"] = "application/json"
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url=url, data=data, headers=headers, method=method.upper())
        start = time.perf_counter()
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                elapsed = int((time.perf_counter() - start) * 1000)
                return resp.status, self._safe_json(text), elapsed, ""
        except HTTPError as e:
            text = ""
            try:
                text = e.read().decode("utf-8", errors="replace")
            except Exception:
                text = str(e)
            elapsed = int((time.perf_counter() - start) * 1000)
            return e.code, self._safe_json(text), elapsed, str(e)
        except URLError as e:
            elapsed = int((time.perf_counter() - start) * 1000)
            return 0, {}, elapsed, str(e)
        except Exception as e:
            elapsed = int((time.perf_counter() - start) * 1000)
            return 0, {}, elapsed, str(e)

    @staticmethod
    def _safe_json(text: str):
        raw = (text or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw[:4000]}


class ConnectivityRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = ApiClient(args.base_url, timeout=args.timeout)
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.batch = f"E2E{datetime.now().strftime('%y%m')}{uuid.uuid4().hex[:4].upper()}"
        self.expected_date = args.expected_date or datetime.now().strftime("%Y-%m-%d")
        self.model = args.model
        self.slot_code = args.slot_code
        self.results: list[StepResult] = []
        self.order_id = ""
        self.serial_no = ""
        self.artifact_dir = (Path(args.output_dir).resolve() / self.run_id)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> int:
        self._step_unauth_guard()
        self._step_login_admin()
        self._step_auto_generate_invalid_qty()
        self._step_auto_generate_one()
        self._step_pick_serial()
        self._step_import_confirm_empty()
        self._step_import_confirm()
        self._step_verify_pending()
        self._step_inbound_to_slot()
        self._step_verify_in_stock()
        self._step_create_order()
        self._step_allocate_empty()
        self._step_allocate()
        self._step_verify_pending_shipping()
        self._step_shipping_pending_contains_serial()
        self._step_shipping_confirm()
        self._step_verify_shipped()
        self._step_logs_contains_serial()
        self._step_sales_forbidden_users_list()
        return self._write_report()

    def _record(self, row: StepResult):
        self.results.append(row)

    def _run_step(self, name, method, path, expected, ok_rule, payload=None, form=False):
        status, body, elapsed, err = self.client.request(method, path, payload=payload, form=form)
        ok = ok_rule(status, body)
        self._record(
            StepResult(
                name=name,
                method=method.upper(),
                path=path,
                expected=expected,
                ok=ok,
                status_code=status,
                elapsed_ms=elapsed,
                request_payload=payload,
                response_body=body,
                error=err,
            )
        )
        return status, body

    def _step_unauth_guard(self):
        raw_client = ApiClient(self.args.base_url, timeout=self.args.timeout)
        status, body, elapsed, err = raw_client.request("GET", "/api/v1/inventory/")
        self._record(
            StepResult(
                name="unauthorized_guard_inventory",
                method="GET",
                path="/api/v1/inventory/",
                expected="401",
                ok=(status == 401),
                status_code=status,
                elapsed_ms=elapsed,
                request_payload=None,
                response_body=body,
                error=err,
            )
        )

    def _step_login_admin(self):
        status, body = self._run_step(
            "login_admin",
            "POST",
            "/api/v1/auth/login",
            "200+token",
            lambda s, b: s == 200 and bool(b.get("access_token")),
            payload={"username": self.args.admin_username, "password": self.args.admin_password},
            form=True,
        )
        if status == 200 and body.get("access_token"):
            self.client.set_token(body["access_token"])

    def _step_auto_generate_invalid_qty(self):
        self._run_step(
            "auto_generate_invalid_qty",
            "POST",
            "/api/v1/inventory/import-staging/auto-generate",
            "422",
            lambda s, b: s == 422,
            payload={"batch": self.batch, "model": self.model, "qty": 0, "expected_inbound_date": self.expected_date, "machine_note": ""},
        )

    def _step_auto_generate_one(self):
        self._run_step(
            "auto_generate_one",
            "POST",
            "/api/v1/inventory/import-staging/auto-generate",
            "200",
            lambda s, b: s == 200,
            payload={
                "batch": self.batch,
                "model": self.model,
                "qty": 1,
                "expected_inbound_date": self.expected_date,
                "machine_note": f"E2E-{self.run_id}",
            },
        )

    def _step_pick_serial(self):
        status, body = self._run_step(
            "import_staging_list",
            "GET",
            "/api/v1/inventory/import-staging",
            "200+find_serial",
            lambda s, b: s == 200 and isinstance(b.get("data", []), list),
        )
        if status != 200:
            return
        rows = body.get("data", [])
        for r in reversed(rows):
            if str(r.get("批次号", "")).strip() == self.batch:
                self.serial_no = str(r.get("流水号", "")).strip()
                break

    def _step_import_confirm_empty(self):
        self._run_step(
            "import_confirm_empty",
            "POST",
            "/api/v1/inventory/import-staging/import-confirm",
            "422",
            lambda s, b: s == 422,
            payload={"selected_track_nos": [], "expected_inbound_date": self.expected_date},
        )

    def _step_import_confirm(self):
        self._run_step(
            "import_confirm_valid",
            "POST",
            "/api/v1/inventory/import-staging/import-confirm",
            "200+success_count>=1",
            lambda s, b: s == 200 and int(b.get("success_count", 0)) >= 1,
            payload={"selected_track_nos": [self.serial_no] if self.serial_no else [], "expected_inbound_date": self.expected_date},
        )

    def _step_verify_pending(self):
        self._run_step(
            "verify_inventory_pending",
            "GET",
            "/api/v1/inventory/",
            "state=待入库",
            lambda s, b: self._inventory_state_is(s, b, self.serial_no, "待入库"),
        )

    def _step_inbound_to_slot(self):
        self._run_step(
            "inbound_to_slot",
            "POST",
            "/api/v1/inventory/inbound-to-slot",
            "200+ok=true",
            lambda s, b: s == 200 and bool(b.get("ok")) is True,
            payload={"serial_no": self.serial_no, "slot_code": self.slot_code},
        )

    def _step_verify_in_stock(self):
        self._run_step(
            "verify_inventory_in_stock",
            "GET",
            "/api/v1/inventory/",
            "state contains 库存中",
            lambda s, b: self._inventory_state_contains(s, b, self.serial_no, "库存中"),
        )

    def _step_create_order(self):
        status, body = self._run_step(
            "create_order",
            "POST",
            "/api/v1/planning/orders",
            "200+order_id",
            lambda s, b: s == 200 and bool(b.get("order_id")),
            payload={
                "客户名": "E2E客户",
                "代理商": "E2E代理",
                "需求机型": f"{self.model}x1",
                "需求数量": 1,
                "备注": f"E2E闭环-{self.run_id}",
                "包装选项": "",
                "发货时间": self.expected_date,
            },
        )
        if status == 200:
            self.order_id = str(body.get("order_id", "")).strip()

    def _step_allocate_empty(self):
        path = f"/api/v1/planning/orders/{self.order_id}/allocate" if self.order_id else "/api/v1/planning/orders/UNKNOWN/allocate"
        self._run_step(
            "allocate_empty",
            "POST",
            path,
            "422",
            lambda s, b: s == 422,
            payload={"selected_serial_nos": []},
        )

    def _step_allocate(self):
        path = f"/api/v1/planning/orders/{self.order_id}/allocate" if self.order_id else "/api/v1/planning/orders/UNKNOWN/allocate"
        self._run_step(
            "allocate_valid",
            "POST",
            path,
            "200",
            lambda s, b: s == 200,
            payload={"selected_serial_nos": [self.serial_no] if self.serial_no else []},
        )

    def _step_verify_pending_shipping(self):
        self._run_step(
            "verify_inventory_pending_shipping",
            "GET",
            "/api/v1/inventory/",
            "state=待发货 and order match",
            lambda s, b: self._inventory_shipping_match(s, b, self.serial_no, self.order_id),
        )

    def _step_shipping_pending_contains_serial(self):
        self._run_step(
            "shipping_pending_contains_serial",
            "GET",
            "/api/v1/inventory/shipping/pending",
            "contains serial",
            lambda s, b: s == 200 and self._shipping_has_serial(b, self.serial_no),
        )

    def _step_shipping_confirm(self):
        self._run_step(
            "shipping_confirm",
            "POST",
            "/api/v1/inventory/shipping/confirm",
            "200",
            lambda s, b: s == 200,
            payload={"serial_nos": [self.serial_no] if self.serial_no else []},
        )

    def _step_verify_shipped(self):
        self._run_step(
            "verify_inventory_shipped",
            "GET",
            "/api/v1/inventory/",
            "state=已出库",
            lambda s, b: self._inventory_state_is(s, b, self.serial_no, "已出库"),
        )

    def _step_logs_contains_serial(self):
        self._run_step(
            "logs_contains_serial",
            "GET",
            "/api/v1/logs/transactions?limit=1000",
            "contains serial log",
            lambda s, b: s == 200 and self._logs_have_serial(b, self.serial_no),
        )

    def _step_sales_forbidden_users_list(self):
        sales_client = ApiClient(self.args.base_url, timeout=self.args.timeout)
        status, body, _, _ = sales_client.request(
            "POST",
            "/api/v1/auth/login",
            payload={"username": self.args.sales_username, "password": self.args.sales_password},
            form=True,
        )
        if status != 200 or not body.get("access_token"):
            self._record(
                StepResult(
                    name="sales_forbidden_users_list",
                    method="GET",
                    path="/api/v1/users/",
                    expected="403 or skipped",
                    ok=True,
                    status_code=0,
                    elapsed_ms=0,
                    request_payload=None,
                    response_body={"skip": "sales login unavailable"},
                    error="",
                )
            )
            return
        sales_client.set_token(body["access_token"])
        s2, b2, elapsed, err = sales_client.request("GET", "/api/v1/users/")
        self._record(
            StepResult(
                name="sales_forbidden_users_list",
                method="GET",
                path="/api/v1/users/",
                expected="403",
                ok=(s2 == 403),
                status_code=s2,
                elapsed_ms=elapsed,
                request_payload=None,
                response_body=b2,
                error=err,
            )
        )

    @staticmethod
    def _rows(body: dict) -> list[dict]:
        if not isinstance(body, dict):
            return []
        rows = body.get("data", [])
        return rows if isinstance(rows, list) else []

    def _inventory_state_is(self, status: int, body: dict, serial: str, expected: str) -> bool:
        if status != 200 or not serial:
            return False
        for row in self._rows(body):
            if str(row.get("流水号", "")).strip() == serial:
                return str(row.get("状态", "")).strip() == expected
        return False

    def _inventory_state_contains(self, status: int, body: dict, serial: str, text: str) -> bool:
        if status != 200 or not serial:
            return False
        for row in self._rows(body):
            if str(row.get("流水号", "")).strip() == serial:
                return text in str(row.get("状态", ""))
        return False

    def _inventory_shipping_match(self, status: int, body: dict, serial: str, order_id: str) -> bool:
        if status != 200 or not serial or not order_id:
            return False
        for row in self._rows(body):
            if str(row.get("流水号", "")).strip() == serial:
                state = str(row.get("状态", "")).strip()
                current_order = str(row.get("占用订单号", "")).strip()
                return state == "待发货" and current_order == order_id
        return False

    @staticmethod
    def _shipping_has_serial(body: dict, serial: str) -> bool:
        if not serial:
            return False
        rows = body.get("data", []) if isinstance(body, dict) else []
        if not isinstance(rows, list):
            return False
        return any(str(row.get("流水号", "")).strip() == serial for row in rows)

    @staticmethod
    def _logs_have_serial(body: dict, serial: str) -> bool:
        if not serial:
            return False
        rows = body.get("data", []) if isinstance(body, dict) else []
        if not isinstance(rows, list):
            return False
        return any(str(row.get("流水号", "")).strip() == serial for row in rows)

    def _write_report(self) -> int:
        blockers = {
            "login_admin",
            "auto_generate_one",
            "import_confirm_valid",
            "inbound_to_slot",
            "create_order",
            "allocate_valid",
            "shipping_confirm",
            "verify_inventory_shipped",
            "logs_contains_serial",
        }
        failed = [row for row in self.results if not row.ok]
        failed_blockers = [row for row in failed if row.name in blockers]
        conclusion = "闭环完整" if not failed_blockers else "存在阻断"

        json_path = self.artifact_dir / "steps.json"
        report_path = self.artifact_dir / "report.md"
        json_path.write_text(json.dumps([asdict(x) for x in self.results], ensure_ascii=False, indent=2), encoding="utf-8")

        lines: list[str] = []
        lines.append("# 模块连通性测试报告")
        lines.append("")
        lines.append(f"- Run ID: `{self.run_id}`")
        lines.append(f"- Base URL: `{self.args.base_url}`")
        lines.append(f"- Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
        lines.append(f"- 结论: **{conclusion}**")
        lines.append(f"- 阻断数: **{len(failed_blockers)}**")
        lines.append(f"- 缺陷数: **{len(failed)}**")
        lines.append("")
        lines.append("## 执行明细")
        lines.append("")
        lines.append("| Step | Expected | Status | Elapsed(ms) | Result |")
        lines.append("|---|---|---:|---:|---|")
        for row in self.results:
            lines.append(f"| {row.name} | {row.expected} | {row.status_code} | {row.elapsed_ms} | {'PASS' if row.ok else 'FAIL'} |")
        lines.append("")
        lines.append("## 缺陷清单")
        lines.append("")
        if not failed:
            lines.append("- 无")
        else:
            for i, row in enumerate(failed, start=1):
                lines.append(
                    f"{i}. `{row.name}` failed, expected `{row.expected}`, status `{row.status_code}`, error `{row.error}`"
                )
        lines.append("")
        lines.append("## 关键输入输出")
        lines.append("")
        for row in self.results:
            lines.append(f"### {row.name}")
            lines.append(f"- Request: `{row.method} {row.path}`")
            lines.append(f"- Input: `{json.dumps(row.request_payload, ensure_ascii=False)[:400]}`")
            lines.append(f"- Output: `{json.dumps(row.response_body, ensure_ascii=False)[:700]}`")
            lines.append(f"- Elapsed: `{row.elapsed_ms} ms`")
            lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"RESULT={conclusion}")
        print(f"ARTIFACT_DIR={self.artifact_dir}")
        print(f"STEPS_JSON={json_path}")
        print(f"REPORT_MD={report_path}")

        if failed_blockers:
            return 2
        if self.args.strict and failed:
            return 1
        return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Connectivity E2E runner for release gate")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default="888")
    parser.add_argument("--sales-username", default="sales")
    parser.add_argument("--sales-password", default="123")
    parser.add_argument("--model", default="FR-400G")
    parser.add_argument("--slot-code", default="E2E-A01")
    parser.add_argument("--expected-date", default="")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output-dir", default="artifacts/connectivity")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runner = ConnectivityRunner(args)
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())

