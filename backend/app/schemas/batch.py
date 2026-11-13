"""[담당: 장수민] 일괄 접수 요청·응답 (명세 v1.4 4.4-1, 4.4-2)."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import DocumentStatus, LotRecommendation
from app.schemas.extraction import Summary


class UploadedDocument(BaseModel):
    document_id: str
    file_name: str
    status: DocumentStatus
    receipt_id: str | None = Field(description="입고 CSV 의 file_name 으로 바로 연결된 입고 건. 없으면 추출 후 로트로 연결")


class RejectedFile(BaseModel):
    file_name: str
    code: str = Field(description="에러 코드 (예: INVALID_FILE, DUPLICATE_FILE)")
    message: str
    duplicates: list[dict] | None = Field(
        None, description="DUPLICATE_FILE 일 때 같은 파일의 기존 문서 [{document_id, file_name, status, uploaded_at, uploaded_by, archived}]")


class BatchUploadResponse(BaseModel):
    batch_id: str
    documents: list[UploadedDocument]
    rejected: list[RejectedFile] = Field(description="접수하지 않은 파일 (형식·크기 오류). 나머지 파일은 접수된다")
    receipts: int = Field(description="입고 CSV 행 수")
    linked_by_file: int = Field(description="file_name 으로 바로 연결된 문서 수")


class ReceiptOut(BaseModel):
    receipt_id: str
    supplier: str | None
    material_code: str
    received_lot_no: str
    spec_set_code: str | None
    received_date: date | None
    file_name: str | None


class BatchQueueItem(BaseModel):
    priority: int = Field(description="1 부적합, 2 서류 불일치, 3 판정 불가·누락·확인 필요, 4 정상, 5 처리 중. 격리 문서는 0")
    priority_label: str
    document_id: str
    file_name: str
    supplier: str | None
    lot_no: str | None
    received_lot_no: str | None
    receipt_id: str | None
    spec_set_code: str | None
    status: DocumentStatus
    lot_recommendation: LotRecommendation | None
    document_issues: list[str] = Field(description="문서 정합성 오류 코드")
    summary: Summary | None
    error_message: str | None


class BatchSummary(BaseModel):
    total: int
    reject: int
    document_issue: int
    hold: int
    approve: int
    processing: int
    isolated: int


class BatchDetail(BaseModel):
    batch_id: str
    material_code: str
    created_by: str
    created_at: datetime
    summary: BatchSummary
    queue: list[BatchQueueItem] = Field(description="검토 순서대로 (부적합 → 서류 불일치 → 판정 불가·누락·확인 필요 → 정상 → 처리 중)")
    isolated: list[BatchQueueItem] = Field(description="추출 실패 문서 (CoA 가 아니거나 읽을 수 없음)")
    unmatched_receipts: list[ReceiptOut] = Field(description="CoA 가 연결되지 않은 입고 건 (CoA 미접수)")
