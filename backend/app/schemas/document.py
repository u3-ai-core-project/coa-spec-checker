"""[담당: 장수민] 문서 업로드·목록·상세 응답 (명세 4.4~4.6)."""
from datetime import date, datetime

from pydantic import BaseModel

from app.core.enums import DocumentStatus, FinalDecision, LotRecommendation
from app.schemas.extraction import Summary


class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    status: DocumentStatus


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
    error_message: str | None


class DocumentDetail(BaseModel):
    document_id: str
    file_name: str
    supplier: str | None
    material_code: str
    material_name: str | None
    po_no: str | None
    lot_no: str | None
    received_lot_no: str | None
    test_date: date | None
    origin: str | None
    applied_standard: str | None
    spec_grade: str | None
    status: DocumentStatus
    lot_recommendation: LotRecommendation | None
    final_decision: FinalDecision | None
    decision_reason: str | None
    error_message: str | None
    uploaded_by: str
    uploaded_at: datetime
    approved_by: str | None
    approved_at: datetime | None
