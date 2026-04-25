from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Request
import pandas as pd
from sqlalchemy import text

from crud.audit_logs import append_audit_log
from crud.users import get_all_users, save_all_users, create_pending_user, user_exists
from crud.roles import role_exists
from api.routes.auth import require_permissions
from database import get_engine

router = APIRouter()

@router.get("/")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query(""),
    role: str = Query(""),
    keyword: str = Query(""),
    _ctx: dict = Depends(require_permissions("USER_MANAGE")),
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
                text(
                    "SELECT username, role, name, status, "
                    "DATE_FORMAT(register_time, '%Y-%m-%d') AS register_time, "
                    "DATE_FORMAT(audit_time, '%Y-%m-%d') AS audit_time, "
                    "auditor "
                    f"FROM users{where_sql} "
                    "ORDER BY users.register_time DESC "
                    "LIMIT :limit OFFSET :skip"
                ),
                conn,
                params=params,
            )
        df = df.where(df.notnull(), None)
        return {"data": df.to_dict(orient="records"), "total": total, "skip": skip, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
def replace_users(data: List[Dict[str, Any]], request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    """Replace all users."""
    import pandas as pd
    try:
        df = pd.DataFrame(data)
        success = save_all_users(df)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save users")
            
        operator = str(_ctx.get("name") or _ctx.get("username") or "system").strip()
        append_audit_log(
            user_id=_ctx.get("username"),
            username=operator,
            action_type="全量替换",
            module="用户管理",
            biz_type="用户",
            content=f"全量替换所有用户数据，共 {len(df)} 条"
        )
        return {"message": "Users updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from typing import Literal

from pydantic import BaseModel, Field, field_validator

class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=64)

    @field_validator("username", "password", "name", "role")
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
    role: str | None = Field(default=None, max_length=50)
    status: Literal["active", "pending", "rejected"] | None = None
    name: str | None = None

@router.post("/register")
def register_user(user: UserCreate, request: Request):
    """Register a new pending user."""
    try:
        if user_exists(user.username):
            raise HTTPException(status_code=400, detail="User already exists")
        if not role_exists(user.role):
            raise HTTPException(status_code=422, detail="申请角色不存在")
        
        new_row = create_pending_user(
            username=user.username,
            password=user.password,
            role=user.role,
            name=user.name
        )
        
        append_audit_log(
            user_id=user.username,
            username=user.name,
            action_type="注册",
            module="用户管理",
            biz_type="用户",
            content=f"新用户注册：{user.name} ({user.username})"
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
def audit_user(payload: UserAuditPayload, request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    try:
        username = str(payload.username).strip().lower()
        
        with get_engine().begin() as conn:
            # 先检查用户是否存在
            result = conn.execute(
                text("SELECT username FROM users WHERE LOWER(TRIM(username)) = :username"),
                {"username": username}
            )
            if not result.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")
            
            if payload.action == "reject":
                # 拒绝时直接删除该用户
                conn.execute(
                    text("DELETE FROM users WHERE LOWER(TRIM(username)) = :username"),
                    {"username": username}
                )
                msg = "用户已被拒绝并删除"
            else:
                # 批准时修改状态
                conn.execute(
                    text("UPDATE users SET status = 'active', audit_time = NOW(), auditor = :auditor WHERE LOWER(TRIM(username)) = :username"),
                    {"username": username, "auditor": str(payload.auditor or "system").strip()}
                )
                msg = "审核成功"
        operator = str(_ctx.get("name") or _ctx.get("username") or "system").strip()
        append_audit_log(
            module="用户管理",
            action_type="审核" if payload.action == "approve" else "拒绝",
            biz_type="用户",
            content=f"{msg}：{payload.username}",
            user_id=_ctx.get("username"),
            username=operator,
        )
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{username}")
def patch_user(username: str, payload: UserPatchPayload, request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    try:
        un = str(username).strip().lower()
        
        # 检查用户是否存在
        with get_engine().connect() as conn:
            result = conn.execute(
                text("SELECT username FROM users WHERE LOWER(TRIM(username)) = :username"),
                {"username": un}
            )
            if not result.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")
        
        # 构建动态更新语句
        update_fields = []
        params = {"username": un}
        
        if payload.role is not None:
            role_value = str(payload.role).strip()
            if not role_value:
                raise HTTPException(status_code=422, detail="角色不能为空")
            if not role_exists(role_value):
                raise HTTPException(status_code=422, detail="角色不存在")
            update_fields.append("role = :role")
            params["role"] = role_value
        if payload.status is not None:
            update_fields.append("status = :status")
            params["status"] = payload.status
        if payload.name is not None:
            v = str(payload.name).strip()
            if not v:
                raise HTTPException(status_code=422, detail="姓名不能为空")
            update_fields.append("name = :name")
            params["name"] = v
        
        if not update_fields:
            return {"message": "无更新内容"}
        
        # 执行单独UPDATE，不影响其他用户
        with get_engine().begin() as conn:
            sql = f"UPDATE users SET {', '.join(update_fields)} WHERE LOWER(TRIM(username)) = :username"
            conn.execute(text(sql), params)
        operator = str(_ctx.get("name") or _ctx.get("username") or "system").strip()
        changed_fields = [k for k, v in payload.model_dump().items() if v is not None]
        append_audit_log(
            module="用户管理",
            action_type="修改",
            biz_type="用户",
            content=f"修改用户：{username}；字段：{', '.join(changed_fields) or '无'}",
            user_id=_ctx.get("username"),
            username=operator,
        )
        return {"message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
