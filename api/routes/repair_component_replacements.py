"""Internal V8 write endpoint for verified Caigou repair replacements."""

import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from config import REPAIR_IDENTITY_API_KEY
from crud.repair_component_replacements import ComponentReplacementConflict, apply_component_replacements

router = APIRouter()


class RepairComponentReplacementRequest(BaseModel):
    idempotencyKey: str = Field(min_length=1, max_length=180)
    repairOutboundNo: str = Field(min_length=1, max_length=100)
    operator: str = Field(default="caigou-repair", max_length=100)
    replacements: list[dict[str, Any]] = Field(min_length=1)


@router.post("")
@router.post("/")
def replace_component_bindings(
    payload: RepairComponentReplacementRequest,
    api_key: str | None = Header(default=None, alias="X-V8-API-KEY"),
):
    configured_key = str(REPAIR_IDENTITY_API_KEY or "").strip()
    if not configured_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="V8 维修接口未配置")
    if not api_key or not hmac.compare_digest(api_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="V8 服务身份验证失败")
    try:
        return {"data": apply_component_replacements(payload.model_dump())}
    except ComponentReplacementConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
