"""Internal, read-only V8 model component catalogue for Repair/Caigou."""

import hmac

from fastapi import APIRouter, Header, HTTPException, Query, status

from config import REPAIR_IDENTITY_API_KEY
from crud.repair_catalog import find_repair_model_components, find_repair_models

router = APIRouter()


def require_v8_service_key(api_key: str | None) -> None:
    configured_key = str(REPAIR_IDENTITY_API_KEY or "").strip()
    if not configured_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="V8 维修接口未配置")
    if not api_key or not hmac.compare_digest(api_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="V8 服务身份验证失败")


@router.get("/models")
def lookup_repair_models(api_key: str | None = Header(default=None, alias="X-V8-API-KEY")):
    require_v8_service_key(api_key)
    return {"data": [
        {"code": row["model_name"], "name": row["model_name"], "series": row["model_family"] or "V8 机型", "sortOrder": row["sort_order"]}
        for row in find_repair_models()
    ]}


@router.get("")
@router.get("/")
def lookup_repair_model_components(
    model_name: str = Query(..., alias="modelName", min_length=1, max_length=150),
    api_key: str | None = Header(default=None, alias="X-V8-API-KEY"),
):
    require_v8_service_key(api_key)

    rows = find_repair_model_components(model_name)
    return {"data": [
        {
            "code": row["position_code"],
            "positionCode": row["position_code"],
            "serialPrefix": row["position_code"],
            # The catalogue only knows the component position. A complete
            # material code is formed after the physical serial is supplied.
            "materialCode": "",
            "materialSuffix": "",
            "name": row["item_name"],
            "type": row["item_category"],
            "spec": row["position_code"],
            "shootingRequirement": row["shooting_requirement"],
            "required": bool(row["required"]),
            "ocrEnabled": bool(row["ocr_enabled"]),
            "ocrProfile": row["ocr_profile"] or "",
            "sortOrder": row["sort_order"],
        }
        for row in rows
    ]}
