"""[담당: 장수민] POST approve, hold, cancel-approval, GET approval-logs (명세 4.12~4.15)

규칙과 상태 전이는 approval_service 에 있다. 이 파일은 권한 연결과 요청·응답 변환만 한다.
권한: 처분·보류는 USER·ADMIN (get_current_user), 처분 취소는 ADMIN (require_admin, 홍채령 구현).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.approval import (
    ApprovalLogOut, ApproveRequest, ApproveResponse, CancelRequest, HoldRequest, StatusResponse,
)
from app.schemas.common import ApiResponse
from app.services import approval_service

router = APIRouter(prefix="/documents", tags=["approval"])


@router.post("/{document_id}/approve", response_model=ApiResponse[ApproveResponse])
def approve(document_id: str, body: ApproveRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """최종 처분 (승인, 조건부 승인, 불합격)."""
    doc = approval_service.approve(db, document_id, body.decision, body.reason, user)
    return ok(ApproveResponse(
        document_id=doc.id, status=doc.status, lot_recommendation=doc.lot_recommendation,
        final_decision=doc.final_decision, approved_by=doc.approver.name, approved_at=doc.approved_at,
    ))


@router.post("/{document_id}/hold", response_model=ApiResponse[StatusResponse])
def hold(document_id: str, body: HoldRequest, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """보류 (후속 조치 대기). 최종 처분이 아니라 on_hold 상태로 관리한다."""
    doc = approval_service.hold(db, document_id, body.follow_up, body.reason, user)
    return ok(StatusResponse(document_id=doc.id, status=doc.status))


@router.post("/{document_id}/cancel-approval", response_model=ApiResponse[StatusResponse])
def cancel_approval(document_id: str, body: CancelRequest, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    """처분 취소 (관리자 전용). 문서를 in_review 로 되돌린다."""
    doc = approval_service.cancel(db, document_id, body.reason, user)
    return ok(StatusResponse(document_id=doc.id, status=doc.status))


@router.get("/{document_id}/approval-logs", response_model=ApiResponse[list[ApprovalLogOut]])
def list_approval_logs(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """처분·보류·취소 이력, 오래된 순."""
    return ok(approval_service.list_logs(db, document_id))
