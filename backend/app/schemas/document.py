"""[담당: 장수민] 문서 업로드·목록·상세 응답 (명세 4.4~4.6)."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import DocumentStatus, ErrorKind, FinalDecision, LotRecommendation
from app.schemas.extraction import Summary


class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    status: DocumentStatus


class DocumentDeleteRequest(BaseModel):
    """DELETE /documents/{id} 본문. 사유 필수 (검사는 deletion_service.clean_reason, 400 REASON_REQUIRED)."""
    reason: str | None = Field(None, description="삭제 사유 (2~500자, 필수)")


class DocumentDeleted(BaseModel):
    """DELETE /documents/{id}."""
    document_id: str


class DocumentListItem(BaseModel):
    document_id: str
    file_name: str
    file_size: int
    supplier: str | None
    material_name: str | None
    lot_no: str | None
    status: DocumentStatus
    lot_recommendation: LotRecommendation | None
    final_decision: FinalDecision | None
    summary: Summary | None
    uploaded_by: str
    uploaded_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    retention_until: datetime | None = None  # 운영 정책 1장: 보관 기간 만료 시각 (처분 완료 문서만)
    archived_at: datetime | None = None      # 원본을 보관용 폴더로 옮긴 시각
    last_activity_at: datetime | None = None  # 운영 정책 1장: 마지막 활동(수정·확인·처분·보류 등, 조회 제외)
    stale_notified_at: datetime | None = None  # 방치(정리 후보)로 표시된 시각. 활동하면 비워진다
    is_stale: bool = False                     # 방치 표시 여부 (stale_notified_at 이 있으면 true)
    error_message: str | None
    attempt_count: int = 0                 # 운영 정책 4장: 추출 시도 횟수
    failed_stage: str | None = None        # 실패 단계 (extract, judge, timeout, interrupted)
    error_kind: ErrorKind | None = None    # 영구(permanent) / 일시(transient) 오류


class DocumentDetail(BaseModel):
    document_id: str
    file_name: str
    supplier: str | None
    material_code: str
    material_name: str | None
    po_no: str | None
    lot_no: str | None
    lot_nos: list[str] = []            # 운영 정책 8.1: 복수 로트 문서면 CoA 에서 읽은 로트 전체 (lot_no 는 null)
    is_multi_lot: bool = False
    received_lot_no: str | None
    test_date: date | None
    origin: str | None
    applied_standard: str | None
    spec_grade: str | None
    spec_set_code: str | None = None  # v1.4안: 판정에 쓴 규격 세트 (예: LI2CO3-D1-2023)
    spec_version: str | None = None   # v1.4안: 규격 버전 (예: YS/T 582-2023)
    batch_id: str | None = None       # v1.4: 일괄 접수(UC01)로 올린 문서면 그 묶음 ID
    reissue_status: str = "none"       # 운영 정책 8.2: none / conflict / review_needed / resolved
    status: DocumentStatus
    lot_recommendation: LotRecommendation | None
    final_decision: FinalDecision | None
    decision_reason: str | None
    error_message: str | None
    attempt_count: int = 0
    failed_stage: str | None = None
    error_kind: ErrorKind | None = None
    uploaded_by: str
    uploaded_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    retention_until: datetime | None = None  # 운영 정책 1장: 보관 기간 만료 시각 (처분 완료 문서만)
    archived_at: datetime | None = None      # 원본을 보관용 폴더로 옮긴 시각
    last_activity_at: datetime | None = None  # 운영 정책 1장: 마지막 활동(수정·확인·처분·보류 등, 조회 제외)
    stale_notified_at: datetime | None = None  # 방치(정리 후보)로 표시된 시각. 활동하면 비워진다
    is_stale: bool = False                     # 방치 표시 여부 (stale_notified_at 이 있으면 true)
