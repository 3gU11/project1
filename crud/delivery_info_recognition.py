"""交付信息（东莞回传合同）附件机台号自动识别。

业务口径（2026-11-11）：
- 东莞回传的订货合同只含机台编号（如 ``9608306``）与客户信息；
- V8 内部机台流水号形如 ``96-08-306``，两边去掉非数字后可以比对；
- 合同附件里还有电话（11 位）、价格（125000）、日期（202610）等干扰数字，
  因此不能"看到数字就当机台号"，必须与 V8 东莞机台流水号归一化比对后才算命中；
- 识别只回填 ``delivery_info_uploads.machine_nos`` 给操作人员参考，
  不自动绑定订单/机台，也不触发发货。

文件支持：
- ``.pdf``：优先 pypdf 文本层；无文本层时提取页内图片逐张调用本机 OCR 服务；
- ``.jpg/.jpeg/.png``：调用本机 OCR 服务；
- ``.docx``：mammoth 提取原始文本；
- ``.doc``：暂不支持（只 warning，不抛错）。

容错原则：OCR 服务未启动/超时、PDF 损坏、依赖缺失等一律只记 warning，
返回可用的空结果，绝不把异常抛给上传/处理业务。
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text

from config import BASE_DIR
from crud.inventory import customer_warehouse_location_sql
from database import get_engine

logger = logging.getLogger(__name__)

# 本机 OCR 服务（server/ocr_service.py，由 run_fullstack.ps1 启动）。
OCR_SERVICE_URL = os.environ.get("OCR_SERVICE_URL", "http://127.0.0.1:8010/ocr")
OCR_TIMEOUT_SECONDS = 20.0
# 单次识别给 OCR 的总预算：多张图片时避免一次上传请求被拖到几分钟。
OCR_TOTAL_BUDGET_SECONDS = 25.0
MAX_PDF_PAGES = 5
MAX_OCR_IMAGES = 5
MAX_MACHINE_NOS = 50
MAX_TEXT_CHARS = 100_000

# 机台号两种写法：内部流水号 ``96-08-306``、合同上的连写 ``9608306``。
_SEPARATOR = "[-‐‑‒–—―－]"
_CANDIDATE_RE = re.compile(
    rf"(?P<hyphen>(?<!\d)\d{{2}}\s*{_SEPARATOR}\s*\d{{2}}\s*{_SEPARATOR}\s*\d{{1,3}}(?!\d))"
    rf"|(?P<plain>(?<!\d)\d{{6,9}}(?!\d))"
)

_MACHINE_SELECT_SQL = (
    "SELECT `流水号` AS serial_no, `机型` AS model, `客户` AS customer, "
    "`占用订单号` AS order_no, `状态` AS status, `Location_Code` AS location_code "
    "FROM finished_goods_data WHERE "
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def normalize_machine_number(value: object) -> str:
    """机台号归一化：只保留数字（``96-08-306`` 与 ``9608306`` 归一后一致）。"""
    return re.sub(r"\D", "", str(value or ""))


def extract_machine_candidates(machine_text: str) -> list[str]:
    """按出现顺序提取文本中的机台号候选（原始写法，已去重）。

    候选口径：2-2-1~3 位带横线的内部流水号，以及 6~9 位连续数字。
    11 位手机号、更长的数字串、价格等由前后数字边界与后续比对过滤。
    """
    candidates: list[str] = []
    seen: set[str] = set()
    for match in _CANDIDATE_RE.finditer(str(machine_text or "")):
        raw = match.group(0).strip()
        key = normalize_machine_number(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(raw)
        if len(candidates) >= 200:
            break
    return candidates


def _row_serial(row: Mapping[str, Any]) -> str:
    return _clean(row.get("serial_no") or row.get("流水号"))


def _row_field(row: Mapping[str, Any], english: str, chinese: str) -> str:
    return _clean(row.get(english) or row.get(chinese))


def _build_machine_index(machines: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for row in machines or []:
        normalized = normalize_machine_number(_row_serial(row))
        if not normalized or normalized in index:
            continue
        index[normalized] = row
    return index


def _machine_payload(row: Mapping[str, Any], matched_text: str = "") -> dict[str, Any]:
    serial = _row_serial(row)
    model = _row_field(row, "model", "机型")
    customer = _row_field(row, "customer", "客户")
    order_no = _row_field(row, "order_no", "占用订单号")
    status = _row_field(row, "status", "状态")
    location = _row_field(row, "location_code", "Location_Code")
    return {
        # 英文键给新接口/脚本用，中文键直接对应「客户成品」页面表格列，前端可原样渲染。
        "serial_no": serial,
        "流水号": serial,
        "model": model,
        "机型": model,
        "customer": customer,
        "客户": customer,
        "order_no": order_no,
        "占用订单号": order_no,
        "status": status,
        "状态": status,
        "location_code": location,
        "Location_Code": location,
        "matched_text": matched_text,
    }


def _load_dongguan_machines() -> list[dict[str, Any]]:
    """加载东莞机台（客户含“东莞”或库位为客户仓），与 crud/inventory.py 同一库位口径。"""
    sql = (
        _MACHINE_SELECT_SQL
        + "(`客户` LIKE :keyword OR "
        + customer_warehouse_location_sql("`Location_Code`")
        + ")"
    )
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql), {"keyword": "%东莞%"}).mappings().all()
    return [dict(row) for row in rows]


def match_machine_numbers(
    machine_text: str,
    machines: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """从文本中识别东莞机台号。

    ``machines`` 为空时从数据库加载东莞机台；测试可传入假机台列表。
    返回 ``{machine_nos, raw_numbers, machines, candidates}``：
    - ``machine_nos``：命中的 V8 内部流水号（如 ``96-08-306``），按出现顺序去重；
    - ``raw_numbers``：未命中但形如 7 位纯数字的合同机台号（保留原样，供人工判断）；
    - ``machines``：命中机台的流水号/机型/客户/占用订单号/状态/Location_Code；
    - ``candidates``：全部候选原始写法（调试用）。
    """
    if machines is None:
        machines = _load_dongguan_machines()
    index = _build_machine_index(machines)
    candidates = extract_machine_candidates(machine_text)
    machine_nos: list[str] = []
    raw_numbers: list[str] = []
    machines_out: list[dict[str, Any]] = []
    seen_serials: set[str] = set()
    seen_raw: set[str] = set()
    for candidate in candidates:
        normalized = normalize_machine_number(candidate)
        row = index.get(normalized)
        if row is not None:
            serial = _row_serial(row)
            if serial and serial not in seen_serials:
                seen_serials.add(serial)
                machine_nos.append(serial)
                machines_out.append(_machine_payload(row, candidate))
        elif candidate.isdigit() and len(candidate) == 7 and candidate not in seen_raw:
            seen_raw.add(candidate)
            raw_numbers.append(candidate)
        if len(machine_nos) >= MAX_MACHINE_NOS and len(raw_numbers) >= MAX_MACHINE_NOS:
            break
    return {
        "machine_nos": machine_nos[:MAX_MACHINE_NOS],
        "raw_numbers": raw_numbers[:MAX_MACHINE_NOS],
        "machines": machines_out[:MAX_MACHINE_NOS],
        "candidates": candidates,
    }


def _extract_pdf_text(file_path: str, warnings: list[str]) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - 依赖已锁定在 requirements.txt
        warnings.append(f"pypdf 不可用，无法解析 PDF：{exc}")
        return "", ""

    try:
        reader = PdfReader(file_path)
        pages = list(reader.pages)[:MAX_PDF_PAGES]
    except Exception as exc:
        warnings.append(f"PDF 读取失败：{exc}")
        return "", ""

    texts: list[str] = []
    for page in pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception as exc:
            warnings.append(f"PDF 文本提取失败：{exc}")
    text = "\n".join(item.strip() for item in texts if item.strip())
    if text.strip():
        return text, "pdf-text"

    # 扫描件（无文本层）：提取页内图片交给本机 OCR。
    warnings.append("PDF 无文本层，改用 OCR 识别页内图片")
    ocr_texts: list[str] = []
    deadline = time.monotonic() + OCR_TOTAL_BUDGET_SECONDS
    image_count = 0
    for page in pages:
        try:
            page_images = list(page.images)
        except Exception as exc:
            warnings.append(f"PDF 页内图片提取失败：{exc}")
            continue
        for image in page_images:
            if image_count >= MAX_OCR_IMAGES:
                warnings.append(f"页内图片超过 {MAX_OCR_IMAGES} 张，仅识别前 {MAX_OCR_IMAGES} 张")
                break
            if time.monotonic() >= deadline:
                warnings.append("OCR 总时长预算已用尽，剩余图片未识别")
                break
            image_count += 1
            temp_path = _write_pdf_image(image, warnings)
            if not temp_path:
                continue
            try:
                ocr_text = _ocr_image(temp_path, warnings, deadline)
            finally:
                _remove_temp(temp_path)
            if ocr_text:
                ocr_texts.append(ocr_text)
    if not ocr_texts:
        warnings.append("PDF 页内图片 OCR 未取得文本")
        return "", "pdf-ocr"
    return "\n".join(ocr_texts), "pdf-ocr"


def _write_pdf_image(image: Any, warnings: list[str]) -> str:
    """把 pypdf 的页内图片落成临时文件；优先转 PNG，兼容 OCR 服务支持的格式。"""
    name = _clean(getattr(image, "name", "")) or "image.png"
    suffix = os.path.splitext(name)[1].lower() or ".png"
    try:
        temp_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(temp_dir, exist_ok=True)
        if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
            # JPEG2000 等格式 OCR 未必支持，先尝试用 Pillow 转成 PNG。
            pil_image = image.image
            file_descriptor, temp_path = tempfile.mkstemp(prefix=".ocr-image-", suffix=".png", dir=temp_dir)
            os.close(file_descriptor)
            pil_image.convert("RGB").save(temp_path, format="PNG")
            return temp_path
        data = image.data
        if not data:
            return ""
        file_descriptor, temp_path = tempfile.mkstemp(prefix=".ocr-image-", suffix=suffix, dir=temp_dir)
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(data)
        return temp_path
    except Exception as exc:
        warnings.append(f"PDF 页内图片导出失败：{exc}")
        return ""


def _remove_temp(temp_path: str) -> None:
    try:
        if temp_path and os.path.isfile(temp_path):
            os.remove(temp_path)
    except OSError:
        pass


def _post_ocr(image_path: str, timeout: float) -> str:
    """调用本机 OCR 服务，返回 raw_text（测试会 monkeypatch 该函数）。"""
    payload = json.dumps({"image_path": image_path}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        OCR_SERVICE_URL,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    if not data.get("success", False):
        raise RuntimeError(_clean(data.get("error")) or "OCR 服务返回失败")
    return _clean(data.get("raw_text"))


def _ocr_image(image_path: str, warnings: list[str], deadline: float | None = None) -> str:
    remaining = OCR_TOTAL_BUDGET_SECONDS if deadline is None else deadline - time.monotonic()
    if remaining <= 0.5:
        warnings.append("OCR 总时长预算已用尽，跳过图片识别")
        return ""
    timeout = max(1.0, min(OCR_TIMEOUT_SECONDS, remaining))
    try:
        return _post_ocr(image_path, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        warnings.append(f"OCR 服务不可用（{type(exc).__name__}）：{exc}")
    except Exception as exc:
        warnings.append(f"OCR 识别失败：{exc}")
    return ""


def _extract_docx_text(file_path: str, warnings: list[str]) -> tuple[str, str]:
    try:
        import mammoth
    except Exception as exc:
        warnings.append(f"mammoth 不可用，无法解析 Word：{exc}")
        return "", ""
    try:
        with open(file_path, "rb") as handle:
            result = mammoth.extract_raw_text(handle)
        return _clean(getattr(result, "value", "")), "docx"
    except Exception as exc:
        warnings.append(f"Word 文档读取失败：{exc}")
        return "", ""


def _extract_text(file_path: str, warnings: list[str]) -> tuple[str, str]:
    extension = os.path.splitext(file_path)[1].lower()
    if extension == ".pdf":
        return _extract_pdf_text(file_path, warnings)
    if extension in {".jpg", ".jpeg", ".png"}:
        return _ocr_image(file_path, warnings), "ocr"
    if extension == ".docx":
        return _extract_docx_text(file_path, warnings)
    if extension == ".doc":
        warnings.append("暂不支持 .doc（Word 97-2003），请另存为 .docx 或 PDF 后重新上传")
        return "", ""
    warnings.append(f"不支持的文件类型：{extension or '未知'}")
    return "", ""


def recognize_delivery_info_file(file_path: str) -> dict[str, Any]:
    """识别交付信息附件中的东莞机台号（任何异常都只记 warning，不抛出）。"""
    result: dict[str, Any] = {
        "text": "",
        "method": "",
        "machine_nos": [],
        "raw_numbers": [],
        "machines": [],
        "candidates": [],
        "warnings": [],
    }
    warnings: list[str] = result["warnings"]
    path = _clean(file_path)
    if not path or not os.path.isfile(path):
        warnings.append(f"交付信息附件不存在：{path or '(空路径)'}")
        return result

    try:
        text, method = _extract_text(path, warnings)
    except Exception as exc:  # 兜底：解析层不允许把异常抛给业务
        warnings.append(f"附件解析失败：{exc}")
        text, method = "", ""
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        warnings.append(f"附件文本过长，仅使用前 {MAX_TEXT_CHARS} 个字符识别机台号")
    result["text"] = text
    result["method"] = method

    try:
        matched = match_machine_numbers(text)
    except Exception as exc:
        warnings.append(f"机台号比对失败：{exc}")
        matched = {"machine_nos": [], "raw_numbers": [], "machines": [], "candidates": []}
    result["machine_nos"] = matched["machine_nos"]
    result["raw_numbers"] = matched["raw_numbers"]
    result["machines"] = matched["machines"]
    result["candidates"] = matched["candidates"]
    if not result["machine_nos"] and not result["raw_numbers"]:
        warnings.append("未识别到 V8 东莞机台号")
    return result


def _resolve_abs_file(file_path: str) -> str:
    path = _clean(file_path)
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def _fetch_upload_row(upload_id: int) -> dict[str, Any] | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT `id`, `file_path`, `file_name`, `status`, `machine_nos` "
                "FROM delivery_info_uploads WHERE id=:id LIMIT 1"
            ),
            {"id": upload_id},
        ).mappings().first()
    return dict(row) if row else None


def _save_upload_machine_nos(upload_id: int, machine_nos_text: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE delivery_info_uploads SET `machine_nos`=:value WHERE `id`=:id"),
            {"value": machine_nos_text[:2000], "id": upload_id},
        )


def recognize_delivery_info_upload(
    upload_id: int,
    *,
    file_path: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """按上传记录重新识别并回填 ``delivery_info_uploads.machine_nos``。

    - 命中内部流水号时回填 ``96-08-306``（多个用 ``、`` 分隔）；
    - 未命中时回填 7 位 raw 数字，便于人工核对；
    - ``status=processed`` 的记录只返回识别结果、不回填（已处理合同不再改机台号）；
    - 附件不存在、库不可用、OCR 失败等只返回 warning，不抛错。
    """
    result: dict[str, Any] = {
        "uploadId": str(upload_id),
        "status": "",
        "text": "",
        "method": "",
        "machine_nos": [],
        "raw_numbers": [],
        "machines": [],
        "candidates": [],
        "warnings": [],
        "machine_nos_text": "",
        "persisted": False,
    }
    warnings: list[str] = result["warnings"]

    row: dict[str, Any] | None = None
    try:
        row = _fetch_upload_row(upload_id)
    except Exception as exc:
        warnings.append(f"读取交付信息上传记录失败：{exc}")
    if row is None:
        if file_path is None:
            warnings.append("交付信息上传记录不存在，无法识别")
            return result
    else:
        result["status"] = _clean(row.get("status"))
        file_path = file_path or _clean(row.get("file_path"))

    abs_path = _resolve_abs_file(file_path or "")
    if not abs_path or not os.path.isfile(abs_path):
        warnings.append(f"交付信息附件不存在：{abs_path or '(空路径)'}")
        return result

    recognized = recognize_delivery_info_file(abs_path)
    result.update(
        {
            "text": recognized["text"],
            "method": recognized["method"],
            "machine_nos": recognized["machine_nos"],
            "raw_numbers": recognized["raw_numbers"],
            "machines": recognized["machines"],
            "candidates": recognized["candidates"],
        }
    )
    warnings.extend(recognized["warnings"])
    machine_nos_text = "、".join(result["machine_nos"]) or "、".join(result["raw_numbers"])
    result["machine_nos_text"] = machine_nos_text

    if not persist or not machine_nos_text:
        return result
    if result["status"] == "processed":
        warnings.append("该记录已处理，仅返回识别结果，未回填机台号")
        return result
    try:
        _save_upload_machine_nos(upload_id, machine_nos_text)
        result["persisted"] = True
    except Exception as exc:
        warnings.append(f"回填机台号失败：{exc}")
    return result
