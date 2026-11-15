"""[담당: 장수민] 재발행 버전 충돌 응답·요청 (운영 정책 8.2)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import DocumentStatus, FinalDecision, LotRecommendation

ReissueStatus = Literal["none", "conflict", "review_needed", "resolved"]


class ReissueVersion(BaseModel):
    """같은 로트의 CoA 1건. 두 문서를 나란히 보여 줄 때 쓴다."""
    document_id: str
    file_name: str
    supplier: str | None
    lot_no: str | None
    status: DocumentStatus
    lot_recommendation: LotRecommendation | None
    final_decision: FinalDecision | None
    uploaded_at: datetime
    approved_at: datetime | None
    is_base: bool


class ReissueInfo(BaseModel):
    """GET /reissue/{document_id}.

    none: 같은 로트의 다른 CoA 없음 / conflict: 기준 버전을 골라야 함 /
    review_needed: 이미 처분된 로트에 재발행본이 들어옴 (처분은 바꾸지 않고 재검토 대상) / resolved: 기준 버전 선택됨
    """
    status: ReissueStatus
    material_code: str
    lot_no: str | None
    base_document_id: str | None
    decided_reason: str | None
    versions: list[ReissueVersion]


class ReissueBaseRequest(BaseModel):
    """POST /reissue/{document_id}/base. 사유는 필수 (검사는 reissue_service 에서 한다)."""
    base_document_id: str = Field(description="기준 버전으로 정할 문서. 같은 로트 묶음 안의 문서여야 한다")
    reason: str | None = Field(None, description="기준 버전을 고른 사유 (필수)")


class ReissueAttentionGroup(BaseModel):
    """GET /reissue/conflicts 의 로트 묶음 1개."""
    material_code: str
    lot_no: str | None
    status: ReissueStatus
    document_ids: list[str]
