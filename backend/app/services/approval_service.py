"""[담당: 장수민] 처분·보류·취소 규칙과 상태 전이, review_status 동기화 (명세 2.6, 2.7, 4.12~4.15).

원칙: 시스템은 권고(lot_recommendation)만 하고 최종 처분(final_decision)은 담당자가 정한다.
두 값은 따로 저장해 "권고 ≠ 처분"을 리포트·대시보드에서 볼 수 있게 한다.

상태 전이
  extracted / in_review / on_hold ──approve──▶ approved (final_decision 기록)
  extracted / in_review / on_hold ──hold─────▶ on_hold   (이미 보류여도 후속 조치를 추가로 기록할 수 있음)
  approved ──cancel-approval (ADMIN)─────────▶ in_review (처분 정보 비움)

검사 순서 (먼저 걸리는 오류를 돌려준다)
  문서 없음 404 → 상태 409 → 처분 규칙 422 → 사유 누락 400

모든 변경은 approval_logs 에 남긴다. 동시에 처분하지 않도록 문서 행을 잠그고 처리한다.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import (
    ApprovalAction, DocumentStatus, FinalDecision, FollowUp, LotRecommendation, NOT_READY_STATUSES,
)
from app.core.errors import AppException, ErrorCode
from app.models import ApprovalLog, Document, User
from app.schemas.approval import ApprovalLogOut
from app.schemas.extraction import ExtractionItem
from app.services import extraction_service, reissue_service
from app.services.judgement.item_judge import REASON_NO_SPEC
from app.services.judgement.policy import default_policy

# 로트 권고와 "같은" 처분 (명세 4.12). 보류 권고에는 대응하는 처분이 없어 어떤 처분이든 사유가 필요하다.
MATCHING_DECISION = {
    LotRecommendation.APPROVE: FinalDecision.ACCEPT,
    LotRecommendation.REJECT: FinalDecision.REJECT,
}


# ---------------------------------------------------------------------------
# 최종 처분 (4.12)
# ---------------------------------------------------------------------------
def approve(db: Session, document_id: str, decision: FinalDecision, reason: str | None, user: User) -> Document:
    doc = _lock(db, document_id)
    _ensure_open(doc)
    reason = _clean(reason)
    # 같은 로트의 CoA 가 여러 개면 기준 버전을 먼저 골라야 한다 (운영 정책 8.2)
    reissue_service.ensure_can_approve(db, doc)

    # 신뢰도 낮음 항목을 확인·수정하지 않았으면 처분 불가
    pending = pending_low_confidence_items(doc)
    if pending:
        raise AppException(ErrorCode.PENDING_LOW_CONFIDENCE_ITEMS,
                           f"신뢰도 낮음 항목을 먼저 확인해야 합니다: {', '.join(pending)}")
    # 부적합 로트는 승인 불가 (불합격 또는 조건부 승인만)
    if doc.lot_recommendation == LotRecommendation.REJECT and decision == FinalDecision.ACCEPT:
        raise AppException(ErrorCode.INVALID_DECISION)
    # 조건부 승인, 권고와 다른 처분은 사유 필수
    if needs_reason(doc.lot_recommendation, decision) and not reason:
        raise AppException(ErrorCode.REASON_REQUIRED,
                           "조건부 승인이거나 로트 권고와 다른 처분은 사유를 입력해야 합니다")

    doc.status = DocumentStatus.APPROVED
    doc.final_decision = decision
    doc.decision_reason = reason
    doc.approved_by = user.id
    # DB 시각으로 기록하고 다시 읽는다. 다른 일시 값과 같이 DB 세션 시간대(+09:00)로 응답된다
    doc.approved_at = func.now()
    _finish(db, doc, ApprovalAction.APPROVE, user, reason=reason, decision=decision)
    db.refresh(doc)
    return doc


def needs_reason(recommendation: LotRecommendation | None, decision: FinalDecision) -> bool:
    """조건부 승인이거나 처분이 로트 권고와 다르면 True (명세 4.12). 프론트 안내 문구 판단에도 같은 기준."""
    if decision == FinalDecision.CONDITIONAL_ACCEPT:
        return True
    return MATCHING_DECISION.get(recommendation) != decision


def pending_low_confidence_items(doc: Document) -> list[str]:
    """신뢰도 기준값 미만인데 담당자가 확인·수정하지 않은 항목명 (명세 4.12).

    판정 결과 JSON 의 reviewed(검수 API 가 기록) 를 기준으로 본다. 기준값은 판정과 같은 설정값.
    사내 규격에 없는 참고 항목(B, D10 등)은 판정·로트 권고에 쓰지 않으므로 처분 차단에서 뺀다
    (10.25 회의 결정 8). AI 가 추정한 미등록 항목(UNMAPPED_ITEM)은 reason_code 가 있어 참고가 아니다.
    """
    result = extraction_service.get_result(doc)
    if result is None:
        return []
    threshold = default_policy().threshold
    return [i.normalized_name for i in result.items
            if i.confidence is not None and i.confidence < threshold and not i.reviewed
            and not is_reference_item(i)]


def is_reference_item(item: ExtractionItem) -> bool:
    """사내 규격에 없어 참고로만 기록된 항목 (판정하지 않음, reason_code 없음)."""
    return item.reason_code is None and item.judgement_reason == REASON_NO_SPEC


# ---------------------------------------------------------------------------
# 보류 (4.13)
# ---------------------------------------------------------------------------
def hold(db: Session, document_id: str, follow_up: FollowUp, reason: str | None, user: User) -> Document:
    doc = _lock(db, document_id)
    _ensure_open(doc)
    reason = _clean(reason)
    if not reason:
        raise AppException(ErrorCode.REASON_REQUIRED, "보류 사유를 입력해야 합니다")

    doc.status = DocumentStatus.ON_HOLD
    _finish(db, doc, ApprovalAction.HOLD, user, reason=reason, follow_up=follow_up)
    return doc


# ---------------------------------------------------------------------------
# 처분 취소 (4.14, ADMIN — 권한 검사는 라우터의 require_admin)
# ---------------------------------------------------------------------------
def cancel(db: Session, document_id: str, reason: str | None, user: User) -> Document:
    doc = _lock(db, document_id)
    if doc.status != DocumentStatus.APPROVED:
        raise AppException(ErrorCode.NOT_APPROVED)
    reason = _clean(reason)
    if not reason:
        raise AppException(ErrorCode.REASON_REQUIRED, "처분 취소 사유를 입력해야 합니다")

    doc.status = DocumentStatus.IN_REVIEW
    doc.final_decision = None
    doc.decision_reason = None
    doc.approved_by = None
    doc.approved_at = None
    _finish(db, doc, ApprovalAction.CANCEL, user, reason=reason)
    return doc


# ---------------------------------------------------------------------------
# 이력 (4.15)
# ---------------------------------------------------------------------------
def list_logs(db: Session, document_id: str) -> list[ApprovalLogOut]:
    if db.get(Document, document_id) is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    rows = db.scalars(
        select(ApprovalLog).options(joinedload(ApprovalLog.user))
        .where(ApprovalLog.document_id == document_id)
        .order_by(ApprovalLog.created_at, ApprovalLog.id)
    )
    return [
        ApprovalLogOut(action=r.action, decision=r.decision, follow_up=r.follow_up, user_name=r.user.name,
                       reason=r.reason, created_at=r.created_at)
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------
def _lock(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id, with_for_update=True, populate_existing=True)
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    return doc


def _ensure_open(doc: Document) -> None:
    """처분·보류가 가능한 상태인지 (extracted, in_review, on_hold)."""
    if doc.status == DocumentStatus.APPROVED:
        raise AppException(ErrorCode.ALREADY_APPROVED)
    if doc.status in NOT_READY_STATUSES:
        raise AppException(ErrorCode.NOT_READY)


def _clean(reason: str | None) -> str | None:
    return (reason or "").strip() or None


def _finish(db: Session, doc: Document, action: ApprovalAction, user: User, *, reason: str | None,
            decision: FinalDecision | None = None, follow_up: FollowUp | None = None) -> None:
    """이력 기록, JSON review_status 동기화, 저장."""
    extraction_service.sync_review_status(doc)
    db.add(ApprovalLog(document_id=doc.id, action=action, decision=decision, follow_up=follow_up,
                       user_id=user.id, reason=reason))
    db.commit()
