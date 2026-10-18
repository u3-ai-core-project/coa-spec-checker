"""[담당: 장수민] GET·PATCH /documents/{id}/extraction..., POST .../confirm, GET .../review-logs (명세 4.8~4.11)

규칙과 상태 처리는 review_service 에 있다. 이 파일은 요청·응답 변환만 한다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.extraction import ExtractionResult
from app.schemas.review import ConfirmResponse, ItemUpdateRequest, ItemUpdateResponse, ReviewLogOut
from app.services import review_service

router = APIRouter(prefix="/documents", tags=["extraction"])


@router.get("/{document_id}/extraction", response_model=ApiResponse[ExtractionResult])
def get_extraction(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """추출·판정 결과 (명세 2.1 JSON 그대로). 추출 전·실패 문서는 409 NOT_READY."""
    return ok(review_service.get_extraction(db, document_id))


@router.patch("/{document_id}/extraction/{item_id}", response_model=ApiResponse[ItemUpdateResponse])
def update_item(
    document_id: str,
    item_id: str,
    body: ItemUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """값 수정, 회신값(실측값·검출한계·자체 시험값) 입력, 항목명 수정. 판정은 서버가 다시 계산한다."""
    item, result, logs = review_service.update_item(db, document_id, item_id, body, user)
    return ok(ItemUpdateResponse(
        item=review_service.to_reviewed_item(item),
        lot_recommendation=result.lot_recommendation,
        summary=result.summary,
        review_logs=[review_service.to_log_out(log) for log in logs],
    ))


@router.post("/{document_id}/extraction/{item_id}/confirm", response_model=ApiResponse[ConfirmResponse])
def confirm_item(
    document_id: str, item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """값 확인 (값 변경 없음). 신뢰도 낮음 항목은 확인 후 값만으로 다시 판정한다."""
    item, result, log = review_service.confirm_item(db, document_id, item_id, user)
    return ok(ConfirmResponse(
        item=review_service.to_reviewed_item(item),
        lot_recommendation=result.lot_recommendation,
        summary=result.summary,
        review_log=review_service.to_log_out(log),
    ))


@router.get("/{document_id}/review-logs", response_model=ApiResponse[list[ReviewLogOut]])
def list_review_logs(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return ok(review_service.list_review_logs(db, document_id))
