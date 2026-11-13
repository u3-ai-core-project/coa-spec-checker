"""[담당: 장수민] 재발행 버전 충돌 API (운영 정책 8.2)

GET  /reissue/conflicts           : 기준 버전을 골라야 하거나 재검토가 필요한 로트 묶음
GET  /reissue/{document_id}       : 문서의 같은 로트 CoA 목록과 충돌 상태 (두 문서를 나란히 보여 줄 때)
POST /reissue/{document_id}/base  : 기준 버전 선택 (사유 필수). 고르기 전에는 확정 처분을 할 수 없다
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.reissue import ReissueAttentionGroup, ReissueBaseRequest, ReissueInfo
from app.services import document_service, reissue_service

router = APIRouter(prefix="/reissue", tags=["reissue"])


@router.get("/conflicts", response_model=ApiResponse[list[ReissueAttentionGroup]])
def list_conflicts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return ok(reissue_service.list_attention(db))


@router.get("/{document_id}", response_model=ApiResponse[ReissueInfo])
def get_reissue(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return ok(reissue_service.to_info(db, document_service.get_document(db, document_id)))


@router.post("/{document_id}/base", response_model=ApiResponse[ReissueInfo])
def choose_base(document_id: str, body: ReissueBaseRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    doc = document_service.get_document(db, document_id)
    return ok(reissue_service.choose_base(db, doc, body.base_document_id, body.reason, user))
