import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_DEPS = r"F:\V8\.tools\python-ocr"
deps_dir = os.environ.get("OCR_PYTHON_DEPS", DEFAULT_DEPS)
if deps_dir and deps_dir not in sys.path:
    sys.path.insert(0, deps_dir)

from rapidocr_onnxruntime import RapidOCR  # noqa: E402


SERVER_ROOT = Path(os.environ.get("OCR_IMAGE_ROOT", Path(__file__).resolve().parent))
ENGINE = None


def get_engine():
    global ENGINE
    if ENGINE is None:
        ENGINE = RapidOCR()
    return ENGINE


def resolve_image_path(value):
    raw = str(value or "").strip().strip('"')
    if not raw:
        raise ValueError("image_path is required")
    path = Path(raw)
    if not path.is_absolute():
        path = SERVER_ROOT / path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"image not found: {path}")
    return path


def normalize_items(result):
    items = []
    for row in result or []:
        if len(row) < 3:
            continue
        box, text, score = row[0], str(row[1] or "").strip(), float(row[2] or 0)
        if not text:
            continue
        x = 0.0
        y = 0.0
        try:
            points = box or []
            x = sum(float(p[0]) for p in points) / max(len(points), 1)
            y = sum(float(p[1]) for p in points) / max(len(points), 1)
        except Exception:
            pass
        items.append({"text": text, "confidence": score, "box": box, "x": x, "y": y})
    items.sort(key=lambda item: (round(item["y"] / 60), item["x"]))
    return items


def merged_value(items):
    identifier, _ = best_identifier_match(items)
    if identifier:
        return identifier
    texts = [item["text"] for item in items if item["text"]]
    if not texts:
        return ""
    compact_ok = all(all(ch.isalnum() or ch in "-_./" for ch in text) for text in texts)
    joiner = "" if compact_ok else " "
    return joiner.join(texts).strip()


def best_identifier_match(items):
    candidates = []
    for item in items:
        text = str(item["text"] or "").strip().upper()
        text = text.replace(" ", "").replace("—", "-").replace("–", "-").replace("_", "-")
        matches = re.findall(r"[A-Z]{0,4}\d{3,}-\d{2,}", text)
        for match in matches:
            candidates.append((match, float(item["confidence"] or 0)))
    if not candidates:
        return "", 0.0
    candidates.sort(key=lambda row: (row[1], len(row[0])), reverse=True)
    return candidates[0]


def confidence_value(items):
    _, identifier_score = best_identifier_match(items)
    if identifier_score > 0:
        return identifier_score
    scores = [float(item["confidence"]) for item in items if float(item["confidence"]) > 0]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def build_fields(payload, items):
    value = merged_value(items)
    confidence = confidence_value(items)
    fields = payload.get("fields") or []
    if fields:
        output = []
        for index, field in enumerate(fields):
            field_code = str(field.get("field_code") or field.get("FieldCode") or "").strip()
            field_name = str(field.get("field_name") or field.get("FieldName") or "").strip()
            output.append(
                {
                    "field_code": field_code or f"recognized_text_{index + 1}",
                    "field_name": field_name or "识别文本",
                    "recognized_value": value if index == 0 else "",
                    "value": value if index == 0 else "",
                    "confidence": confidence if index == 0 else 0,
                }
            )
        return output
    return [
        {
            "field_code": "recognized_text",
            "field_name": "识别文本",
            "recognized_value": value,
            "value": value,
            "confidence": confidence,
        }
    ]


def run_ocr(payload):
    image_path = resolve_image_path(payload.get("image_path"))
    start = time.time()
    result, elapsed = get_engine()(str(image_path))
    items = normalize_items(result)
    raw_text = "\n".join(item["text"] for item in items)
    return {
        "success": True,
        "image_path": str(image_path),
        "ocr_profile": payload.get("ocr_profile") or "",
        "position_code": payload.get("position_code") or "",
        "raw_text": raw_text,
        "fields": build_fields(payload, items),
        "items": items,
        "elapsed": elapsed,
        "duration_ms": int((time.time() - start) * 1000),
    }


class OCRHandler(BaseHTTPRequestHandler):
    server_version = "V8LocalOCR/1.0"

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            self.write_json({"status": "ok"})
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/ocr":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8"))
            self.write_json(run_ocr(payload))
        except Exception as exc:
            self.write_json({"success": False, "error": str(exc)}, status=500)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def write_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    host = os.environ.get("OCR_HOST", "127.0.0.1")
    port = int(os.environ.get("OCR_PORT", "8010"))
    get_engine()
    server = ThreadingHTTPServer((host, port), OCRHandler)
    print(f"OCR service listening on http://{host}:{port}/ocr", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
