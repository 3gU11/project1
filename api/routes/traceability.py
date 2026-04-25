import math

from fastapi import APIRouter, Depends
from api.routes.auth import get_current_user_token, require_permissions
from crud.traceability import search_global_summary, get_target_status_distribution, get_target_timeline

router = APIRouter(dependencies=[Depends(get_current_user_token)])

@router.get("/search")
def search_traceability(keyword: str = "", _ctx: dict = Depends(require_permissions("TRACEABILITY"))):
    if not keyword:
        return {"data": []}
    df = search_global_summary(keyword=keyword)
    return {"data": df.to_dict(orient="records")}

@router.get("/{target_id}/status")
def target_status(target_id: str, model: str = "", _ctx: dict = Depends(require_permissions("TRACEABILITY"))):
    df = get_target_status_distribution(target_id, model=model)
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
    return {"data": records}

@router.get("/{target_id}/timeline")
def target_timeline(target_id: str, _ctx: dict = Depends(require_permissions("TRACEABILITY"))):
    df = get_target_timeline(target_id)
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
    return {"data": records}
