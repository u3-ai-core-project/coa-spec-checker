"""[담당: 장수민] 후속 조치·공급사 문의 초안 응답 (명세 v1.4안 4.22 GET /documents/{id}/follow-ups)."""
from pydantic import BaseModel, Field

from app.core.enums import DocumentStatus, FollowUp


class FollowUpLineOut(BaseModel):
    """후속 조치 1건. 예외 항목 1개 또는 문서 정합성 오류 1개."""
    target: str = Field(description="항목명. 문서 정합성 오류면 '문서'")
    code: str = Field(description="사유코드(reason_code) 또는 문서 정합성 오류 코드")
    label: str = Field(description="사유 짧은 이름")
    why: str = Field(description="왜 문제인가 (판정 근거)")
    condition: str = Field(description="해결 조건 (담당자용 문구)")
    raw_value: str | None = Field(description="CoA 원문 값 (근거 인용)")
    to_supplier: bool = Field(description="공급사에 요청할 일인지 (false 면 내부 확인)")


class InquiryDraftOut(BaseModel):
    subject: str
    body: str
    source: str = Field(description="template | ai | template_fallback (AI 실패로 템플릿 사용)")
    lot_nos: list[str | None] = Field(description="초안에 포함된 로트")


class OpenDocumentOut(BaseModel):
    """같은 공급사의 처리 중인 문서 중 공급사 요청이 있는 것."""
    document_id: str
    lot_no: str | None
    status: DocumentStatus
    request_count: int


class FollowUpsResponse(BaseModel):
    document_id: str
    supplier: str | None
    lot_no: str | None
    suggested_follow_up: FollowUp | None = Field(description="보류 화면의 후속 조치 기본값 추천")
    supplier_lines: list[FollowUpLineOut]
    internal_lines: list[FollowUpLineOut]
    draft: InquiryDraftOut | None = Field(description="이 로트만의 문의 초안. 공급사 요청이 없으면 null")
    open_documents: list[OpenDocumentOut] = Field(description="같은 공급사의 처리 중 문서 (이 문서 포함)")
    combined_draft: InquiryDraftOut | None = Field(
        description="같은 공급사의 열린 요청을 메일 1통으로 묶은 초안. 해당 문서가 2건 이상일 때만")
