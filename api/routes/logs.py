from fastapi import APIRouter, HTTPException

from crud.logs import get_transaction_logs

router = APIRouter()


@router.get("/transactions")
def list_transaction_logs(limit: int = 500):
    try:
        limit = max(1, min(int(limit), 5000))
        df = get_transaction_logs(limit=limit)
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
