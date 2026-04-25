from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.routes.auth import get_current_user_token, require_permissions
from crud.audit_logs import append_audit_log
from crud.model_dictionary import (
    delete_model_dictionary_item,
    get_model_dictionary,
    replace_model_name_globally,
    save_model_dictionary,
    seed_model_dictionary_if_empty,
)

router = APIRouter(dependencies=[Depends(get_current_user_token)])


class ModelDictionarySavePayload(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ModelDictionaryReplacePayload(BaseModel):
    old_name: str
    new_name: str


class ModelDictionaryDeletePayload(BaseModel):
    id: int | None = None
    model_name: str


@router.get("/")
def get_dictionary_rows():
    try:
        seed_model_dictionary_if_empty()
        return {"data": get_model_dictionary()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取机型字典失败: {e}")


@router.post("/save")
def save_dictionary_rows(
    payload: ModelDictionarySavePayload,
    request: Request,
    _ctx: dict = Depends(require_permissions("MODEL_DICTIONARY")),
):
    try:
        count = save_model_dictionary(payload.rows)
        operator = str(_ctx.get("name") or _ctx.get("username") or "system").strip()
        append_audit_log(
            module="机型字典",
            action_type="保存",
            biz_type="机型",
            content=f"保存机型字典，共 {count} 条",
            user_id=_ctx.get("username"),
            username=operator,
        )
        return {"message": f"机型字典已保存（{count} 条）", "count": count}
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存机型字典失败: {e}")


@router.post("/replace")
def replace_model_name(
    payload: ModelDictionaryReplacePayload,
    request: Request,
    _ctx: dict = Depends(require_permissions("MODEL_DICTIONARY")),
):
    try:
        result = replace_model_name_globally(payload.old_name, payload.new_name)
        operator = str(_ctx.get("name") or _ctx.get("username") or "system").strip()
        append_audit_log(
            module="机型字典",
            action_type="替换",
            biz_type="机型",
            content=f"机型 {payload.old_name} 替换为 {payload.new_name}，影响 {result.get('total', 0)} 条记录",
            user_id=_ctx.get("username"),
            username=operator,
        )
        return {"message": f"替换完成，共影响 {result.get('total', 0)} 条记录", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"机型替换失败: {e}")


@router.post("/delete")
def delete_model_name(
    payload: ModelDictionaryDeletePayload,
    request: Request,
    _ctx: dict = Depends(require_permissions("MODEL_DICTIONARY")),
):
    try:
        deleted = delete_model_dictionary_item(payload.model_name, payload.id)
        if deleted <= 0:
            raise HTTPException(status_code=404, detail="机型不存在或已删除")
        operator = str(_ctx.get("name") or _ctx.get("username") or "system").strip()
        target = str(payload.model_name or "").strip() or f"ID:{payload.id}"
        append_audit_log(
            module="机型字典",
            action_type="删除",
            biz_type="机型",
            content=f"删除机型：{target}；删除条数：{deleted}",
            user_id=_ctx.get("username"),
            username=operator,
        )
        return {"message": "机型删除成功", "deleted": deleted}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"机型删除失败: {e}")
