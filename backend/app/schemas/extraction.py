"""[담당: 장수민] 추출·판정 결과 JSON 스키마 (명세 2.1) — AI 추출 파트와의 계약.

- ExtractionInput   : AI 추출 파트가 서버로 넘기는 형식 (AI 가 채우는 필드만)
- ExtractionResult  : 서버가 판정까지 채워 extraction_results.result(JSONB) 에 저장하고,
                      GET /documents/{id}/extraction 으로 그대로 반환하는 형식

AI 파트에는 ExtractionInput 과 ExtractedItem 만 맞추면 된다고 전달한다.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    DocumentIssueCode, Judgement, LotRecommendation, MappingSource, ReasonCode, ResolutionType, ReviewStatus,
    ValueQualifier, ValueSource,
)


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
    # AI 제안 칸 (10.25 회의 결정). 저장·표시용이며 판정에는 쓰지 않는다 (값 해석과 비교는 서버 코드가 한다)
    value_kind: str | None = None    # number | bound | nd | spec_copy | pass_text | description
    value_reason: str | None = None  # 값 종류를 그렇게 본 근거 한 줄
    check_reasons: list[str] = Field(default_factory=list)  # AI 자체 검증에 걸린 이유


class ExtractionInput(BaseModel):
    """AI 추출 파트가 문서 1건에 대해 넘기는 결과."""
    model_config = ConfigDict(extra="ignore")

    document_id: str | None = None
    supplier: str | None = None
    lot_no: str | None = None
    # 운영 정책 8.1: 한 문서에서 읽은 로트번호 전체. 로트가 1개면 비워 둬도 된다. lot_no 와 합쳐 2개 이상이면 복수 로트 문서
    lot_nos: list[str] = []
    test_date: date | None = None
    origin: str | None = None
    applied_standard: str | None = None
    # v1.4안 2.5: 제품 불일치·날짜 충돌(document_issues) 판단용 (PR #5 요청, AI 가 CoA 에서 읽은 그대로)
    product_name: str | None = None
    manufacture_date: date | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    retest_date: date | None = None
    items: list[ExtractedItem]


# ---------------------------------------------------------------------------
# 서버가 판정까지 채운 전체 결과 (JSONB 저장, API 응답)
# ---------------------------------------------------------------------------
class Resolution(BaseModel):
    """해결 조건 (명세 v1.4안 2.1). 예외 항목(fail, undetermined, missing, check)에만 붙는다.

    condition 은 화면·리포트·문의 초안에 쓰는 문구이고, operator·threshold·unit 은 서버가
    회신값이 조건을 만족하는지 비교할 때 쓰는 값이다 (비교할 수치가 없는 조건이면 null).
    예) Fe "none detected", 사내 상한 5 ppm
        {"type": "detection_limit", "condition": "검출한계 ≤ 5 ppm",
         "target_item": "Fe", "operator": "<=", "threshold": 5, "unit": "ppm"}
    """
    type: ResolutionType
    condition: str
    target_item: str | None = None  # 값을 받아야 하는 항목 (예: 중금속 총량 → "Pb"). 보통은 이 항목 자신
    operator: Literal["<", "<=", ">="] | None = None
    threshold: float | None = None
    unit: str | None = None


class DocumentIssue(BaseModel):
    """문서 정합성 오류 (명세 v1.4안 2.1). 1개 이상이면 fail 이 없어도 보류 권고 (v1.4안 2.4)."""
    code: DocumentIssueCode
    message: str


class ExtractionItem(ExtractedItem):
    """항목 1개의 전체 필드. AI 필드 + 서버(규칙) 필드."""
    item_id: str
    value_qualifier: ValueQualifier | None = None
    converted_value: float | str | None = None
    detection_limit: float | None = None
    spec_lsl: float | None = None
    spec_usl: float | None = None
    spec_unit: str | None = None  # 사내 규격 단위. converted_value·detection_limit·spec_lsl/usl 의 단위. 규격 없는 항목은 null
    judgement: Judgement
    judgement_reason: str | None = None
    deviation: float | None = None
    reason_code: ReasonCode | None = None    # v1.4안. 적합이면 null
    resolution: Resolution | None = None     # v1.4안. 적합이면 null
    # ---- 검수 상태 (서버 작성, 명세 외 추가) ----
    # 다시 판정할 때(항목명 수정, 규격 재판정, 교차 규칙) 담당자가 확인·입력한 내용을 잃지 않도록 항목에 남긴다.
    # 대시보드 "사람 확인 항목 수"(v1.4안 reviewed_item_ratio)도 reviewed 로 셀 수 있다.
    reviewed: bool = False                   # 담당자가 확인(confirm)하거나 값을 입력함
    value_source: ValueSource | None = None  # 담당자가 값을 입력했으면 그 출처. 원문 값을 쓰는 중이면 null


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
    lot_no: str | None = None        # 복수 로트 문서는 첫 로트만 고르지 않으려고 null 로 두고 lot_nos 에 전체를 담는다
    lot_nos: list[str] = []          # 복수 로트 문서(운영 정책 8.1)일 때만 채운다
    test_date: date | None = None
    origin: str | None = None
    applied_standard: str | None = None
    product_name: str | None = None  # 아래 넷은 ExtractionInput 에서 그대로 옮긴 값
    manufacture_date: date | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    retest_date: date | None = None
    items: list[ExtractionItem]
    document_issues: list[DocumentIssue] = []  # v1.4. 탐지 규칙은 judgement/document_checks.py
    lot_recommendation: LotRecommendation
    summary: Summary
    review_status: ReviewStatus = ReviewStatus.PENDING

    def to_json(self) -> dict:
        """JSONB 저장용 dict. date 는 'YYYY-MM-DD' 문자열, summary 키는 'pass'."""
        return self.model_dump(mode="json", by_alias=True)
