from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.routes.auth import get_current_user_token, require_roles
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
    _ctx: dict = Depends(require_roles("Admin", "Boss")),
):
    try:
        count = save_model_dictionary(payload.rows)
        return {"message": f"机型字典已保存（{count} 条）", "count": count}
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存机型字典失败: {e}")


@router.post("/replace")
def replace_model_name(
    payload: ModelDictionaryReplacePayload,
    _ctx: dict = Depends(require_roles("Admin", "Boss")),
):
    try:
        result = replace_model_name_globally(payload.old_name, payload.new_name)
        return {"message": f"替换完成，共影响 {result.get('total', 0)} 条记录", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"机型替换失败: {e}")


@router.post("/delete")
def delete_model_name(
    payload: ModelDictionaryDeletePayload,
    _ctx: dict = Depends(require_roles("Admin", "Boss")),
):
    try:
        deleted = delete_model_dictionary_item(payload.model_name, payload.id)
        if deleted <= 0:
            raise HTTPException(status_code=404, detail="机型不存在或已删除")
        return {"message": "机型删除成功", "deleted": deleted}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"机型删除失败: {e}")
