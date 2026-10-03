"""[담당: 장수민] 추출·판정 결과 JSON 스키마 (명세 2.1) — AI 추출 파트와의 계약.

- ExtractionInput   : AI 추출 파트가 서버로 넘기는 형식 (AI 가 채우는 필드만)
- ExtractionResult  : 서버가 판정까지 채워 extraction_results.result(JSONB) 에 저장하고,
                      GET /documents/{id}/extraction 으로 그대로 반환하는 형식

AI 파트에는 ExtractionInput 과 ExtractedItem 만 맞추면 된다고 전달한다.
"""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Judgement, LotRecommendation, MappingSource, ReviewStatus, ValueQualifier


class BBox(BaseModel):
    """원본 근거 좌표. page 는 1부터 시작."""
    page: int
    x: float
    y: float
    w: float
    h: float


# ---------------------------------------------------------------------------
# AI 추출 파트 → 서버
# ---------------------------------------------------------------------------
class ExtractedItem(BaseModel):
    """AI 추출 파트가 채우는 항목 필드 (명세 2.1 '필드별 작성 주체')."""
    model_config = ConfigDict(extra="ignore")

    item_id: str | None = None  # 없으면 서버가 부여 (item-001, item-002 ...)
    raw_name: str | None = None
    normalized_name: str
    mapping_source: MappingSource = MappingSource.AI  # AI 파트는 dictionary 또는 ai
    raw_value: str | None = None
    raw_spec: str | None = None
    unit: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    bbox: BBox | None = None


class ExtractionInput(BaseModel):
    """AI 추출 파트가 문서 1건에 대해 넘기는 결과."""
    model_config = ConfigDict(extra="ignore")

    document_id: str | None = None
    supplier: str | None = None
    lot_no: str | None = None
    test_date: date | None = None
    origin: str | None = None
    applied_standard: str | None = None
    items: list[ExtractedItem]


# ---------------------------------------------------------------------------
# 서버가 판정까지 채운 전체 결과 (JSONB 저장, API 응답)
# ---------------------------------------------------------------------------
class ExtractionItem(ExtractedItem):
    """항목 1개의 전체 필드. AI 필드 + 서버(규칙) 필드."""
    item_id: str
    value_qualifier: ValueQualifier | None = None
    converted_value: float | str | None = None
    detection_limit: float | None = None
    spec_lsl: float | None = None
    spec_usl: float | None = None
    judgement: Judgement
    judgement_reason: str | None = None
    deviation: float | None = None


class Summary(BaseModel):
    pass_: int = Field(0, alias="pass")
    fail: int = 0
    undetermined: int = 0
    missing: int = 0
    check: int = 0

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class ExtractionResult(BaseModel):
    document_id: str
    supplier: str | None = None
    lot_no: str | None = None
    test_date: date | None = None
    origin: str | None = None
    applied_standard: str | None = None
    items: list[ExtractionItem]
    lot_recommendation: LotRecommendation
    summary: Summary
    review_status: ReviewStatus = ReviewStatus.PENDING

    def to_json(self) -> dict:
        """JSONB 저장용 dict. date 는 'YYYY-MM-DD' 문자열, summary 키는 'pass'."""
        return self.model_dump(mode="json", by_alias=True)
