from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
import pandas as pd
from sqlalchemy import text

from crud.users import get_all_users, save_all_users, create_pending_user, user_exists
from api.routes.auth import require_roles
from database import get_engine

router = APIRouter()

@router.get("/")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query(""),
    role: str = Query(""),
    keyword: str = Query(""),
    _ctx: dict = Depends(require_roles("Admin", "Boss")),
):
    """Get all users."""
    try:
        where_clauses = []
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if str(status).strip():
            where_clauses.append("`status` = :status")
            params["status"] = str(status).strip()
        if str(role).strip():
            where_clauses.append("`role` = :role")
            params["role"] = str(role).strip()
        if str(keyword).strip():
            where_clauses.append("(`username` LIKE :kw OR `name` LIKE :kw)")
            params["kw"] = f"%{str(keyword).strip()}%"
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with get_engine().connect() as conn:
            total_df = pd.read_sql(text(f"SELECT COUNT(*) AS total FROM users{where_sql}"), conn, params=params)
            total = int(total_df.iloc[0]["total"]) if not total_df.empty else 0
            df = pd.read_sql(
                text(f"SELECT * FROM users{where_sql} ORDER BY register_time DESC LIMIT :limit OFFSET :skip"),
                conn,
                params=params,
            )
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records"), "total": total, "skip": skip, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
def replace_users(data: List[Dict[str, Any]], _ctx: dict = Depends(require_roles("Admin"))):
    """Replace all users."""
    import pandas as pd
    try:
        df = pd.DataFrame(data)
        success = save_all_users(df)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save users")
        return {"message": "Users updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from typing import Literal

from pydantic import BaseModel, Field, field_validator

class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    role: Literal["Boss", "Admin", "Sales", "Prod", "Inbound"]
    name: str = Field(min_length=1, max_length=64)

    @field_validator("username", "password", "name")
    @classmethod
    def strip_and_validate(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value


class UserAuditPayload(BaseModel):
    username: str
    auditor: str = "system"
    action: Literal["approve", "reject"]


class UserPatchPayload(BaseModel):
    role: Literal["Boss", "Admin", "Sales", "Prod", "Inbound"] | None = None
    status: Literal["active", "pending", "rejected"] | None = None
    name: str | None = None

@router.post("/register")
def register_user(user: UserCreate):
    """Register a new pending user."""
    try:
        if user_exists(user.username):
            raise HTTPException(status_code=400, detail="User already exists")
        
        new_row = create_pending_user(
            username=user.username,
            password=user.password,
            role=user.role,
            name=user.name
        )
        return {"message": "User registered successfully", "data": new_row}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit")
def audit_user(payload: UserAuditPayload, _ctx: dict = Depends(require_roles("Admin", "Boss"))):
    try:
        df = get_all_users()
        if df.empty:
            raise HTTPException(status_code=404, detail="用户不存在")
        username = str(payload.username).strip().lower()
        mask = df["username"].astype(str).str.strip().str.lower() == username
        if not mask.any():
            raise HTTPException(status_code=404, detail="用户不存在")
            
        if payload.action == "reject":
            # 拒绝时直接删除该用户
            df = df[~mask]
            msg = "用户已被拒绝并删除"
        else:
            # 批准时修改状态
            df.loc[mask, "status"] = "active"
            df.loc[mask, "audit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df.loc[mask, "auditor"] = str(payload.auditor or "system").strip()
            msg = "审核成功"
            
        if not save_all_users(df):
            raise HTTPException(status_code=500, detail="保存失败")
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{username}")
def patch_user(username: str, payload: UserPatchPayload, _ctx: dict = Depends(require_roles("Admin", "Boss"))):
    try:
        df = get_all_users()
        if df.empty:
            raise HTTPException(status_code=404, detail="用户不存在")
        un = str(username).strip().lower()
        mask = df["username"].astype(str).str.strip().str.lower() == un
        if not mask.any():
            raise HTTPException(status_code=404, detail="用户不存在")
        if payload.role is not None:
            df.loc[mask, "role"] = payload.role
        if payload.status is not None:
            df.loc[mask, "status"] = payload.status
        if payload.name is not None:
            v = str(payload.name).strip()
            if not v:
                raise HTTPException(status_code=422, detail="姓名不能为空")
            df.loc[mask, "name"] = v
        if not save_all_users(df):
            raise HTTPException(status_code=500, detail="保存失败")
        return {"message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
