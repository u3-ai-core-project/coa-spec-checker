"""[담당: 장수민] 처분·보류·취소 요청·응답, approval-logs (명세 4.12~4.15, v1.4안).

reason 은 빈 문자열도 허용하고, 필요한 경우 서비스에서 400 REASON_REQUIRED 로 거절한다
(필드 누락을 400 VALIDATION_ERROR 로 보내면 명세의 REASON_REQUIRED 와 코드가 달라지기 때문).
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ApprovalAction, DocumentStatus, FinalDecision, FollowUp, LotRecommendation


class ApproveRequest(BaseModel):
    decision: FinalDecision = Field(description="accept(승인) | conditional_accept(조건부 승인) | reject(불합격)")
    reason: str | None = Field(None, description="조건부 승인이거나 로트 권고와 다른 처분이면 필수")


class HoldRequest(BaseModel):
    follow_up: FollowUp = Field(description="후속 조치 종류 (v1.4안 3개 추가)")
    reason: str | None = Field(None, description="필수")


class CancelRequest(BaseModel):
    reason: str | None = Field(None, description="필수")


class ApproveResponse(BaseModel):
    """POST /documents/{id}/approve (명세 4.12)."""
    document_id: str
    status: DocumentStatus
    lot_recommendation: LotRecommendation | None
    final_decision: FinalDecision
    approved_by: str
    approved_at: datetime


class StatusResponse(BaseModel):
    """POST hold (4.13), cancel-approval (4.14)."""
    document_id: str
    status: DocumentStatus


class ApprovalLogOut(BaseModel):
    """GET /documents/{id}/approval-logs (명세 4.15)."""
    action: ApprovalAction
    decision: FinalDecision | None
    follow_up: FollowUp | None
    user_name: str
    reason: str | None
    created_at: datetime
