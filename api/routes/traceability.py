from fastapi import APIRouter, Depends
from api.routes.auth import get_current_user_token, require_roles
from crud.traceability import search_global_summary, get_target_status_distribution, get_target_timeline

router = APIRouter(dependencies=[Depends(get_current_user_token)])

@router.get("/search")
def search_traceability(keyword: str = "", _ctx: dict = Depends(require_roles("Admin", "Boss"))):
    if not keyword:
        return {"data": []}
    df = search_global_summary(keyword)
    return {"data": df.to_dict(orient="records")}

@router.get("/{target_id}/status")
def target_status(target_id: str, _ctx: dict = Depends(require_roles("Admin", "Boss"))):
    df = get_target_status_distribution(target_id)
    return {"data": df.to_dict(orient="records")}

@router.get("/{target_id}/timeline")
def target_timeline(target_id: str, _ctx: dict = Depends(require_roles("Admin", "Boss"))):
    df = get_target_timeline(target_id)
    return {"data": df.to_dict(orient="records")}
