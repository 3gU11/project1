"""Internal, read-only V8 identity endpoint used by Caigou repair processing."""

import hmac

from fastapi import APIRouter, Header, HTTPException, Query, status

from config import REPAIR_IDENTITY_API_KEY
from crud.repair_identity import find_repair_identity, find_repair_machine_identity

router = APIRouter()


@router.get("")
@router.get("/")
def lookup_repair_identity(
    board_no: str = Query(..., alias="boardNo", min_length=1, max_length=150),
    api_key: str | None = Header(default=None, alias="X-V8-API-KEY"),
):
    configured_key = str(REPAIR_IDENTITY_API_KEY or "").strip()
    if not configured_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="V8 维修身份接口未配置")
    if not api_key or not hmac.compare_digest(api_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="V8 服务身份验证失败")

    identity = find_repair_identity(board_no)
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到有效的 V8 零部件绑定")
    return {"data": identity}


@router.get("/machine")
def lookup_repair_machine_identity(
    machine_no: str = Query(..., alias="machineNo", min_length=1, max_length=150),
    api_key: str | None = Header(default=None, alias="X-V8-API-KEY"),
):
    configured_key = str(REPAIR_IDENTITY_API_KEY or "").strip()
    if not configured_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="V8 维修身份接口未配置")
    if not api_key or not hmac.compare_digest(api_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="V8 服务身份验证失败")
    identity = find_repair_machine_identity(machine_no)
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到有效的 V8 机床档案")
    return {"data": identity}
