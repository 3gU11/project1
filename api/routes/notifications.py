import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.routes.auth import get_current_user_context, require_permissions
from database import get_engine


router = APIRouter(dependencies=[Depends(require_permissions("NOTIFICATION_VIEW"))])


class ReadVersion(BaseModel):
    version: int = Field(ge=1)


def _user(user=Depends(get_current_user_context)):
    return str(user["username"])


@router.get("")
def list_notifications(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                       unread: bool = False, username: str = Depends(_user)):
    where = "WHERE COALESCE(r.read_version, 0) < n.version" if unread else ""
    params = {"username": username, "limit": limit, "offset": (page - 1) * limit}
    base = (" FROM contract_notifications n LEFT JOIN contract_notification_reads r "
            "ON r.contract_id=n.contract_id AND r.username=:username ")
    with get_engine().connect() as conn:
        total = conn.execute(text("SELECT COUNT(*)" + base + where), params).scalar_one()
        rows = conn.execute(text("""
            SELECT n.contract_id, n.created_snapshot, n.created_by, n.created_at,
                   n.planned_snapshot, n.planned_by, n.planned_at,
                   n.converted_snapshot, n.converted_by, n.converted_at,
                   n.order_id, n.latest_at, n.version,
                   COALESCE(r.read_version, 0) AS read_version
        """ + base + where + " ORDER BY n.latest_at DESC, n.contract_id DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
    data = []
    for row in rows:
        item = dict(row)
        for key in ("created_snapshot", "planned_snapshot", "converted_snapshot"):
            value = item[key]
            item[key] = json.loads(value) if isinstance(value, str) else value
        for key in ("created_at", "planned_at", "converted_at", "latest_at"):
            item[key] = item[key].isoformat() if item[key] else None
        item["unread"] = item["read_version"] < item["version"]
        data.append(item)
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.get("/unread-count")
def unread_count(username: str = Depends(_user)):
    with get_engine().connect() as conn:
        count = conn.execute(text("""
            SELECT COUNT(*) FROM contract_notifications n
            LEFT JOIN contract_notification_reads r
              ON r.contract_id=n.contract_id AND r.username=:username
            WHERE COALESCE(r.read_version, 0) < n.version
        """), {"username": username}).scalar_one()
    return {"total": count}


@router.post("/{contract_id}/read")
def mark_read(contract_id: str, payload: ReadVersion, username: str = Depends(_user)):
    with get_engine().begin() as conn:
        current = conn.execute(text("SELECT version FROM contract_notifications WHERE contract_id=:cid"),
                               {"cid": contract_id}).scalar_one_or_none()
        if current is None:
            raise HTTPException(status_code=404, detail="消息不存在")
        if payload.version > current:
            raise HTTPException(status_code=409, detail="消息版本无效")
        conn.execute(text("""
            INSERT INTO contract_notification_reads (username, contract_id, read_version)
            VALUES (:username, :cid, :version)
            ON DUPLICATE KEY UPDATE read_version=GREATEST(read_version, VALUES(read_version))
        """), {"username": username, "cid": contract_id, "version": payload.version})
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(username: str = Depends(_user)):
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO contract_notification_reads (username, contract_id, read_version)
            SELECT :username, contract_id, version FROM contract_notifications WHERE version > 0
            ON DUPLICATE KEY UPDATE read_version=GREATEST(read_version, VALUES(read_version))
        """), {"username": username})
    return {"ok": True}
