from uuid import UUID
import httpx
from typing import Literal, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from api.routes.auth import require_permissions
from contract_bridge import client as bridge
from crud import local_contract_drafts as local

router = APIRouter(dependencies=[Depends(require_permissions('DEALER_ORDER_REVIEW'))])

@router.get('/local')
def local_contracts(page: int = Query(1, ge=1, le=10000)):
    return local.list_drafts(page)

class LocalFields(BaseModel):
    fields: dict[str, Any]

@router.put('/local/{draft_id}')
def local_update(draft_id: UUID, payload: LocalFields):
    try:
        row = local.update(str(draft_id), payload.fields)
    except ValueError as error:
        raise HTTPException(409, str(error))
    if not row: raise HTTPException(404, '合同草稿不存在')
    return row

@router.post('/local/{draft_id}/prepare')
def local_prepare(draft_id: UUID):
    try: return local.prepare(str(draft_id))
    except KeyError as error: raise HTTPException(404, str(error))
    except ValueError as error: raise HTTPException(422, str(error))

@router.get('/local/{draft_id}/preview')
def local_preview(draft_id: UUID, preview_hash: str = Query(alias='previewHash', pattern=r'^[a-f0-9]{64}$')):
    row = local.get(str(draft_id))
    if not row or row.get('preview_hash') != preview_hash: raise HTTPException(409, '预览版本已变化，请刷新')
    with local.get_engine().begin() as conn:
        content = conn.execute(__import__('sqlalchemy').text('SELECT preview FROM v8_contract_drafts WHERE id=:id'), {'id': str(draft_id)}).scalar()
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', headers={'Cache-Control': 'no-store'})

class LocalReview(BaseModel):
    previewHash: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['approved', 'rejected']
    note: str = Field(default='', max_length=1000)

@router.post('/local/{draft_id}/review')
def local_review(draft_id: UUID, payload: LocalReview, actor: dict = Depends(require_permissions('DEALER_ORDER_REVIEW'))):
    try: return local.review(str(draft_id), payload.previewHash, payload.decision, str(actor.get('username') or ''), payload.note)
    except ValueError as error: raise HTTPException(409, str(error))


def call(operation, *args):
    try:
        return operation(*args)
    except httpx.HTTPError as error:
        raise HTTPException(503, '合同云端暂不可用，请稍后重试') from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(409, str(error)) from error


@router.get('')
def contracts(page: int = Query(1, ge=1, le=10000)):
    return call(bridge.list_contracts, page)


@router.post('/{revision_id}/prepare')
def prepare(revision_id: UUID):
    return call(bridge.prepare_preview, str(revision_id))


@router.get('/{revision_id}/preview')
def preview(revision_id: UUID, preview_hash: str = Query(alias='previewHash', pattern=r'^[a-f0-9]{64}$')):
    content = call(bridge.preview_file, str(revision_id), preview_hash)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', headers={'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="contract-{revision_id}.docx"'})


class Review(BaseModel):
    previewHash: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['approved', 'rejected']
    note: str = Field(default='', max_length=1000)


@router.post('/{revision_id}/review')
def review(revision_id: UUID, payload: Review, actor: dict = Depends(require_permissions('DEALER_ORDER_REVIEW'))):
    username = str(actor.get('username') or '').strip()
    if not username:
        raise HTTPException(403, '审批人身份无效')
    if payload.decision == 'rejected' and not payload.note.strip():
        raise HTTPException(422, '驳回时请填写原因')
    return call(bridge.review, str(revision_id), payload.previewHash, payload.decision, username, payload.note)
