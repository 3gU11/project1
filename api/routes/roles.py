from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from api.routes.auth import require_permissions
from crud.audit_logs import append_audit_log
from crud.roles import (
    create_role,
    delete_role,
    get_permission_catalog,
    get_role_permissions,
    list_roles,
    set_role_permissions,
    update_role,
)

router = APIRouter()


class RolePayload(BaseModel):
    role_id: str = Field(min_length=1, max_length=50)
    role_name: str = Field(default="", max_length=100)

    @field_validator("role_id", "role_name")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return str(value or "").strip()


class RoleUpdatePayload(BaseModel):
    role_name: str = Field(min_length=1, max_length=100)

    @field_validator("role_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("角色名称不能为空")
        return value


class RolePermissionsPayload(BaseModel):
    permissions: List[str] = Field(default_factory=list)


def _operator(ctx: dict) -> str:
    return str(ctx.get("name") or ctx.get("username") or "system").strip()


@router.get("/")
def get_roles():
    return {"data": list_roles()}


@router.post("/")
def add_role(payload: RolePayload, request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    try:
        row = create_role(payload.role_id, payload.role_name)
        append_audit_log(
            module="角色权限",
            action_type="新增角色",
            biz_type="角色",
            content=f"新增角色：{row['role_id']} / {row['role_name']}",
            user_id=_ctx.get("username"),
            username=_operator(_ctx),
        )
        return {"message": "角色新增成功", "data": row}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"新增角色失败: {exc}")


@router.patch("/{role_id}")
def edit_role(role_id: str, payload: RoleUpdatePayload, request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    try:
        row = update_role(role_id, payload.role_name)
        append_audit_log(
            module="角色权限",
            action_type="修改角色",
            biz_type="角色",
            content=f"修改角色：{row['role_id']} / {row['role_name']}",
            user_id=_ctx.get("username"),
            username=_operator(_ctx),
        )
        return {"message": "角色更新成功", "data": row}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新角色失败: {exc}")


@router.delete("/{role_id}")
def remove_role(role_id: str, request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    try:
        delete_role(role_id, current_role=str(_ctx.get("role") or ""))
        append_audit_log(
            module="角色权限",
            action_type="删除角色",
            biz_type="角色",
            content=f"删除角色：{role_id}",
            user_id=_ctx.get("username"),
            username=_operator(_ctx),
        )
        return {"message": "角色删除成功"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除角色失败: {exc}")


@router.get("/permissions/catalog", dependencies=[Depends(require_permissions("USER_MANAGE"))])
def permissions_catalog():
    return {"data": get_permission_catalog()}


@router.get("/{role_id}/permissions", dependencies=[Depends(require_permissions("USER_MANAGE"))])
def role_permissions(role_id: str):
    return {"role_id": role_id, "permissions": get_role_permissions(role_id)}


@router.put("/{role_id}/permissions")
def save_role_permissions(role_id: str, payload: RolePermissionsPayload, request: Request, _ctx: dict = Depends(require_permissions("USER_MANAGE"))):
    try:
        saved = set_role_permissions(role_id, payload.permissions)
        append_audit_log(
            module="角色权限",
            action_type="保存权限",
            biz_type="角色权限",
            content=f"保存角色 {role_id} 权限：{', '.join(saved)}",
            user_id=_ctx.get("username"),
            username=_operator(_ctx),
        )
        return {"message": "权限保存成功", "role_id": role_id, "permissions": saved}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存角色权限失败: {exc}")
