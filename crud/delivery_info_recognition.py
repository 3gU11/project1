"""交付信息（东莞回传合同）附件自动识别。

业务口径（2026-11-14）：
- 东莞回传的订货合同含机台编号（如 ``9608306``）、购货单位名称/个人姓名与地址；
- V8 内部机台流水号形如 ``96-08-306``，两边去掉非数字后可以比对；
- 合同附件里还有电话（11 位）、价格（125000）、日期（202610）等干扰数字，
  因此不能"看到数字就当机台号"，必须与 V8 东莞机台流水号归一化比对后才算命中；
- 购货单位/地址只取自合同的「购货单位名称/个人姓名」「地址」栏位，
  不会把合同抬头的「需方」（经销商）或签署栏的「单位地址」误当成购货单位；
- 识别结果只回填 ``delivery_info_uploads`` 的 ``buyer_name``/``buyer_address``/
  ``machine_nos``，给 V8 操作人员预填参考，操作人员对照附件核对后手动处理；
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

# 购货方详细资料：合同固定栏位（「购货单位名称/个人姓名」与「地址」）。
# 先匹配完整栏位名，再退回到「购货单位」；「个人姓名」单独出现时也认。
_BUYER_NAME_LABEL_RE = re.compile(r"购货单位名称(?:[/／、]个人姓名)?|购货单位(?!地址)|个人姓名")
_ADDRESS_LABEL_RE = re.compile(r"地址")
# 地址/名称取值的结束标志：购货方资料后面的栏位或合同条款。
_BUYER_STOP_RE = re.compile(
    r"联系人|联系电话|联系方式|其他特殊要求|特殊要求|备注|合计"
    r"|交（提）货|交\(提\)货|需方|供方|单位名称|开户银行"
)
# 值两端的标点/分隔符（OCR 常把表格线、冒号一起识别进来）。
_FIELD_EDGE_CHARS = "：:／/、,，;；.。·| \t\r\n"
MAX_BUYER_NAME_CHARS = 80
MAX_BUYER_ADDRESS_CHARS = 160
# OCR 文本块按视觉行重排时，两行文本框纵向重叠超过较矮者高度的比例即视为同一行。
_ROW_MIN_OVERLAP_RATIO = 0.2


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


def _item_box(item: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    """取 OCR 文本块的外接矩形 (left, top, right, bottom)；无坐标返回 None。"""
    box = item.get("box") or []
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def build_ocr_text_rows(items: Sequence[Mapping[str, Any]] | None) -> str:
    """把 OCR 文本块按视觉行重排成文本。

    OCR 服务的 raw_text 按 ``round(y / 60)`` 分行，字号小或单元格换行时，
    同一行的值可能被排到下一行（例如地址尾部的「37米左右」跑到「联系电话」之后）。
    这里按文本框纵向重叠聚类成行、行内按横坐标排序，恢复表格的阅读顺序。
    """
    entries: list[dict[str, Any]] = []
    for item in items or []:
        text = _clean(item.get("text"))
        box = _item_box(item)
        if not text or box is None:
            continue
        left, top, right, bottom = box
        entries.append(
            {
                "text": text,
                "left": left,
                "top": top,
                "bottom": bottom,
                "height": max(bottom - top, 1.0),
            }
        )
    if not entries:
        return ""
    entries.sort(key=lambda entry: (entry["top"], entry["left"]))
    rows: list[dict[str, Any]] = []
    for entry in entries:
        target = None
        for row in rows:
            overlap = min(row["bottom"], entry["bottom"]) - max(row["top"], entry["top"])
            if overlap > _ROW_MIN_OVERLAP_RATIO * min(row["height"], entry["height"]):
                target = row
                break
        if target is None:
            rows.append(
                {
                    "top": entry["top"],
                    "bottom": entry["bottom"],
                    "height": entry["height"],
                    "items": [entry],
                }
            )
            continue
        target["items"].append(entry)
        target["top"] = min(target["top"], entry["top"])
        target["bottom"] = max(target["bottom"], entry["bottom"])
        target["height"] = max(target["height"], target["bottom"] - target["top"])
    rows.sort(key=lambda row: row["top"])
    return "\n".join(
        " ".join(token["text"] for token in sorted(row["items"], key=lambda token: (token["left"], token["top"])))
        for row in rows
    )


def _compact_text(value: object) -> str:
    """去掉全部空白，把 PDF 文本层拆成多块的中文名称/地址拼回连续文本。"""
    return re.sub(r"\s+", "", str(value or ""))


def _clean_field_value(raw: object, max_chars: int) -> str:
    value = _compact_text(raw).strip(_FIELD_EDGE_CHARS)
    if len(value) > max_chars:
        value = value[:max_chars].rstrip(_FIELD_EDGE_CHARS)
    return value


def _looks_like_text_value(value: str, *, min_chars: int) -> bool:
    if len(value) < min_chars or value.isdigit():
        return False
    return len(re.findall(r"[\u4e00-\u9fff]", value)) >= 2


def _complete_truncated_company_name(name: str, warnings: list[str]) -> str:
    """OCR 把「有限公司」的「司」漏在单元格第二行时补全，并提示操作人员核对。"""
    if name.endswith("有限公"):
        warnings.append(f"购货单位名称疑似截断（{name}），已补全为「{name}司」，请对照附件核对")
        return name + "司"
    return name


def extract_buyer_info(
    text: str,
    items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """从合同文本中提取「购货单位名称/个人姓名」与「地址」。

    - 有 OCR 文本块坐标时先按视觉行重排再取值（修复表格多列串行）；
    - 名称取「购货单位名称/个人姓名」之后、到「地址」栏位之前的值；
    - 地址取「地址」之后、到「联系人」等其他栏位之前的值；
    - 找不到对应栏位时返回空字符串与 warning，不抛异常。
    """
    result: dict[str, Any] = {"buyer_name": "", "buyer_address": "", "warnings": []}
    warnings: list[str] = result["warnings"]
    source = build_ocr_text_rows(items) or text
    compact = _compact_text(source)
    if not compact:
        return result

    name_match = _BUYER_NAME_LABEL_RE.search(compact)
    if name_match is None:
        warnings.append("合同文本中未找到「购货单位名称/个人姓名」栏位")
        return result

    address_match = _ADDRESS_LABEL_RE.search(compact, name_match.end())
    if address_match is None:
        stop_match = _BUYER_STOP_RE.search(compact, name_match.end())
        name_region = compact[name_match.end() : stop_match.start() if stop_match else len(compact)]
        address_region = ""
        warnings.append("合同文本中未找到「地址」栏位")
    else:
        name_region = compact[name_match.end() : address_match.start()]
        stop_match = _BUYER_STOP_RE.search(compact, address_match.end())
        address_region = compact[address_match.end() : stop_match.start() if stop_match else len(compact)]

    buyer_name = _clean_field_value(name_region, MAX_BUYER_NAME_CHARS)
    if _looks_like_text_value(buyer_name, min_chars=2):
        result["buyer_name"] = _complete_truncated_company_name(buyer_name, warnings)
    elif buyer_name:
        warnings.append(f"购货单位名称不像有效值（{buyer_name}），已忽略")

    buyer_address = _clean_field_value(address_region, MAX_BUYER_ADDRESS_CHARS)
    if _looks_like_text_value(buyer_address, min_chars=4):
        result["buyer_address"] = buyer_address
    elif buyer_address:
        warnings.append(f"地址不像有效值（{buyer_address}），已忽略")
    return result


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
            if ocr_text["text"]:
                ocr_texts.append(ocr_text["text"])
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


def _post_ocr(image_path: str, timeout: float) -> dict[str, Any]:
    """调用本机 OCR 服务，返回 ``{"text": raw_text, "items": 文本块坐标}``。

    测试会 monkeypatch 该函数；文本块坐标用于把表格多列的值按视觉行重排。
    """
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
    return {"text": _clean(data.get("raw_text")), "items": data.get("items") or []}


def _ocr_image(image_path: str, warnings: list[str], deadline: float | None = None) -> dict[str, Any]:
    """识别单张图片，返回 ``{"text": ..., "items": [...]}``；失败只记 warning。"""
    remaining = OCR_TOTAL_BUDGET_SECONDS if deadline is None else deadline - time.monotonic()
    if remaining <= 0.5:
        warnings.append("OCR 总时长预算已用尽，跳过图片识别")
        return {"text": "", "items": []}
    timeout = max(1.0, min(OCR_TIMEOUT_SECONDS, remaining))
    try:
        result = _post_ocr(image_path, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        warnings.append(f"OCR 服务不可用（{type(exc).__name__}）：{exc}")
        return {"text": "", "items": []}
    except Exception as exc:
        warnings.append(f"OCR 识别失败：{exc}")
        return {"text": "", "items": []}
    if isinstance(result, str):  # 兼容只返回文本的旧实现/测试桩
        return {"text": _clean(result), "items": []}
    return {"text": _clean(result.get("text")), "items": result.get("items") or []}


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


def _extract_text(file_path: str, warnings: list[str]) -> tuple[str, str, list[dict[str, Any]]]:
    """返回 ``(文本, 识别方式, OCR 文本块坐标)``；非图片路径的坐标为空。"""
    extension = os.path.splitext(file_path)[1].lower()
    if extension == ".pdf":
        return _extract_pdf_text(file_path, warnings) + ([],)
    if extension in {".jpg", ".jpeg", ".png"}:
        ocr = _ocr_image(file_path, warnings)
        return ocr["text"], "ocr", list(ocr["items"])
    if extension == ".docx":
        return _extract_docx_text(file_path, warnings) + ([],)
    if extension == ".doc":
        warnings.append("暂不支持 .doc（Word 97-2003），请另存为 .docx 或 PDF 后重新上传")
        return "", "", []
    warnings.append(f"不支持的文件类型：{extension or '未知'}")
    return "", "", []


def recognize_delivery_info_file(file_path: str) -> dict[str, Any]:
    """识别交付信息附件中的东莞机台号、购货单位/个人姓名与地址（异常只记 warning）。"""
    result: dict[str, Any] = {
        "text": "",
        "method": "",
        "machine_nos": [],
        "raw_numbers": [],
        "machines": [],
        "candidates": [],
        "buyer_name": "",
        "buyer_address": "",
        "warnings": [],
    }
    warnings: list[str] = result["warnings"]
    path = _clean(file_path)
    if not path or not os.path.isfile(path):
        warnings.append(f"交付信息附件不存在：{path or '(空路径)'}")
        return result

    items: list[dict[str, Any]] = []
    try:
        text, method, items = _extract_text(path, warnings)
    except Exception as exc:  # 兜底：解析层不允许把异常抛给业务
        warnings.append(f"附件解析失败：{exc}")
        text, method, items = "", "", []
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

    try:
        buyer = extract_buyer_info(text, items)
    except Exception as exc:  # 购货单位识别同样不允许把异常抛给业务
        warnings.append(f"购货单位/地址识别失败：{exc}")
        buyer = {"buyer_name": "", "buyer_address": "", "warnings": []}
    result["buyer_name"] = buyer["buyer_name"]
    result["buyer_address"] = buyer["buyer_address"]
    warnings.extend(buyer["warnings"])
    if text.strip():
        if not result["buyer_name"]:
            warnings.append("未识别到购货单位名称/个人姓名")
        if not result["buyer_address"]:
            warnings.append("未识别到购货单位地址")
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
                "SELECT `id`, `file_path`, `file_name`, `status`, `machine_nos`, "
                "`buyer_name`, `buyer_address` "
                "FROM delivery_info_uploads WHERE id=:id LIMIT 1"
            ),
            {"id": upload_id},
        ).mappings().first()
    return dict(row) if row else None


def _save_upload_recognition(
    upload_id: int,
    *,
    machine_nos_text: str = "",
    buyer_name: str = "",
    buyer_address: str = "",
) -> None:
    """回填识别结果；只填空值，不覆盖操作人员/小程序已填的内容。"""
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE delivery_info_uploads SET "
                "`machine_nos`=COALESCE(NULLIF(:machine_nos, ''), `machine_nos`), "
                "`buyer_name`=COALESCE(NULLIF(:buyer_name, ''), `buyer_name`), "
                "`buyer_address`=COALESCE(NULLIF(:buyer_address, ''), `buyer_address`) "
                "WHERE `id`=:id"
            ),
            {
                "machine_nos": machine_nos_text[:2000],
                "buyer_name": buyer_name[:200],
                "buyer_address": buyer_address[:500],
                "id": upload_id,
            },
        )


def recognize_delivery_info_upload(
    upload_id: int,
    *,
    file_path: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """按上传记录重新识别并回填购货单位/地址/机台号。

    - 购货单位名称/个人姓名、地址取自合同「购货方详细资料」栏位；
    - 命中内部流水号时回填 ``96-08-306``（多个用 ``、`` 分隔）；
    - 未命中时回填 7 位 raw 数字，便于人工核对；
    - 只填空值，不覆盖上传时已填的购货单位/地址/机台号；
    - ``status=processed`` 的记录只返回识别结果、不回填（已处理合同不再改）；
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
        "buyer_name": "",
        "buyer_address": "",
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
            "buyer_name": recognized.get("buyer_name") or "",
            "buyer_address": recognized.get("buyer_address") or "",
        }
    )
    warnings.extend(recognized["warnings"])
    machine_nos_text = "、".join(result["machine_nos"]) or "、".join(result["raw_numbers"])
    result["machine_nos_text"] = machine_nos_text

    if not persist or not (machine_nos_text or result["buyer_name"] or result["buyer_address"]):
        return result
    if result["status"] == "processed":
        warnings.append("该记录已处理，仅返回识别结果，未回填购货单位/地址/机台号")
        return result
    try:
        _save_upload_recognition(
            upload_id,
            machine_nos_text=machine_nos_text,
            buyer_name=result["buyer_name"],
            buyer_address=result["buyer_address"],
        )
        result["persisted"] = True
    except Exception as exc:
        warnings.append(f"回填识别结果失败：{exc}")
    return result
