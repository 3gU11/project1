from fastapi import APIRouter, HTTPException, Depends

from crud.audit_logs import get_operation_logs
from crud.logs import get_transaction_logs
from api.routes.auth import get_current_user_token, require_permissions

router = APIRouter(dependencies=[Depends(get_current_user_token)])


@router.get("/transactions")
def list_transaction_logs(page: int = 1, page_size: int = 50, days: int = 14):
    try:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        days = max(1, int(days))
        df, total = get_transaction_logs(page=page, page_size=page_size, days=days)
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records"), "total": total, "page": page, "page_size": page_size, "days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit", dependencies=[Depends(require_permissions("LOG_VIEW"))])
def list_audit_logs(
    page: int = 1,
    page_size: int = 50,
    days: int = 14,
    user: str = "",
    module: str = "",
    operation: str = "",
    biz_type: str = "",
    serial_no: str = "",
    contract_no: str = "",
    order_no: str = "",
):
    try:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        days = max(1, int(days))
        df, total = get_operation_logs(
            page=page,
            page_size=page_size,
            days=days,
            user=user,
            module=module,
            operation=operation,
            biz_type=biz_type,
            serial_no=serial_no,
            contract_no=contract_no,
            order_no=order_no,
        )
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records"), "total": total, "page": page, "page_size": page_size, "days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
