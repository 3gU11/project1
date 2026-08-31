import hmac
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config import BASE_DIR, GO_INTERNAL_TOKEN


router = APIRouter()
PHOTO_ROOT = (Path(BASE_DIR) / "server" / "data" / "machine_photo_tasks").resolve()
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024


class QrDecodeRequest(BaseModel):
    image_path: str


def _authorize_internal_request(request: Request) -> None:
    configured = (GO_INTERNAL_TOKEN or "").strip()
    provided = (request.headers.get("X-Internal-Token") or "").strip()
    if configured:
        if not hmac.compare_digest(configured, provided):
            raise HTTPException(status_code=403, detail="Unauthorized internal request")
        return
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Internal QR decoding is local-only")


def _resolve_photo_path(raw_path: str) -> Path:
    image_path = Path(str(raw_path or "").strip()).resolve()
    try:
        image_path.relative_to(PHOTO_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Image path is outside the photo storage directory") from exc
    if not image_path.is_file() or image_path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Image file is invalid")
    if image_path.stat().st_size > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image file is too large")
    return image_path


@router.post("/decode")
def decode_qr(payload: QrDecodeRequest, request: Request):
    _authorize_internal_request(request)
    image_path = _resolve_photo_path(payload.image_path)
    encoded = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Image cannot be decoded")

    detector = cv2.QRCodeDetector()
    values: list[str] = []
    try:
        detected, decoded_values, _, _ = detector.detectAndDecodeMulti(image)
        if detected:
            values.extend(str(value).strip() for value in decoded_values if str(value).strip())
    except cv2.error:
        pass
    if not values:
        value, _, _ = detector.detectAndDecode(image)
        if str(value).strip():
            values.append(str(value).strip())

    unique_values = list(dict.fromkeys(values))
    return {
        "success": bool(unique_values),
        "value": unique_values[0] if len(unique_values) == 1 else "",
        "values": unique_values,
        "ambiguous": len(unique_values) > 1,
    }
