"""Internal, read-only V8 machine component projection for the Repair system.

售后 mobile 端拍照任务收集的机台零部件信息（machine_component_bindings）在这里
按机台流水号只读开放，供维修系统核对机台当前/历史零部件编号。接口与
/api/v1/repair-identity 使用同一把服务端密钥（X-V8-API-KEY），只读、不落库。
"""

import hmac

from fastapi import APIRouter, Header, HTTPException, Query, status

from config import REPAIR_IDENTITY_API_KEY
from crud.repair_machine_components import find_repair_machine_components

router = APIRouter()


def require_v8_service_key(api_key: str | None) -> None:
    configured_key = str(REPAIR_IDENTITY_API_KEY or "").strip()
    if not configured_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="V8 维修接口未配置")
    if not api_key or not hmac.compare_digest(api_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="V8 服务身份验证失败")


@router.get("")
@router.get("/")
def lookup_repair_machine_components(
    machine_no: str = Query(..., alias="machineNo", min_length=1, max_length=150),
    include_inactive: bool = Query(default=False, alias="includeInactive"),
    api_key: str | None = Header(default=None, alias="X-V8-API-KEY"),
):
    """按机台流水号返回拍照任务收集到的零部件信息（只读）。"""
    require_v8_service_key(api_key)
    data = find_repair_machine_components(machine_no, include_inactive=include_inactive)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到有效的 V8 机台零部件信息")
    return {"data": data}
