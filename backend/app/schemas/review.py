"""[담당: 장수민] 항목 수정·확인 요청·응답, review-logs (명세 4.9~4.11, v1.4안).

PATCH 요청은 세 가지 일을 한다 (둘 이상을 한 번에 보내도 된다).
  1. 값 수정     : converted_value (+ value_qualifier)
  2. 회신값 입력 : detection_limit (검출한계), 또는 converted_value + value_source=supplier_reply / internal_test
  3. 항목명 수정 : normalized_name

값 입력 규칙 (서버가 값 해석 없이 바로 판정에 쓰므로 형식을 엄격히 본다)
  - converted_value 는 사내 규격 단위 기준 값이다 (예: ppm 규격이면 0.002 % 가 아니라 20)
  - value_qualifier 를 생략하면 converted_value 가 있으면 exact, detection_limit 만 있으면 not_detected
  - exact / less_than / less_equal : converted_value 는 숫자
  - not_detected                   : converted_value 는 비우고, 검출한계가 있으면 detection_limit
  - text                           : converted_value 는 문자열 (정성 항목)
잘못된 조합은 400 VALIDATION_ERROR.

수정 사유 (reason, 명세 v1.4 4.9)
  - 값을 입력하는 요청(1, 2)은 필수. 비었거나 공백뿐이면 400 REASON_REQUIRED (검사는 review_service 에서 한다.
    필드 누락을 VALIDATION_ERROR 로 보내면 처분·보류 API 의 REASON_REQUIRED 와 코드가 달라지기 때문)
  - 항목명만 고치는 요청(3)은 선택
  - 이번 요청으로 남는 이력(edit, rename)에 같이 저장한다. 결과 JSON 에는 넣지 않는다.
"""
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.enums import (
    Judgement, LotRecommendation, ReasonCode, ReviewAction, ValueQualifier as Q, ValueSource,
)
from app.schemas.extraction import Resolution, Summary
from app.services.judgement.value_parser import ParsedValue

_NUMERIC = {Q.EXACT, Q.LESS_THAN, Q.LESS_EQUAL}


class ItemUpdateRequest(BaseModel):
    converted_value: float | str | None = None
    value_qualifier: Q | None = None
    detection_limit: float | None = Field(None, ge=0, description="검출한계 (v1.4안, 사내 규격 단위)")
    normalized_name: str | None = Field(None, description="사내 표준 항목명으로 수정")
    value_source: ValueSource | None = Field(
        None, description="입력값 출처 (v1.4안): correction(기본) | supplier_reply | internal_test")
    reason: str | None = Field(None, description="수정 사유 (v1.4). 값을 입력할 때 필수, 항목명만 고칠 때 선택")

    @property
    def clean_reason(self) -> str | None:
        """앞뒤 공백을 뺀 사유. 비었으면 None."""
        return (self.reason or "").strip() or None

    @property
    def has_value(self) -> bool:
        return any(v is not None for v in (self.converted_value, self.value_qualifier, self.detection_limit))

    @property
    def new_name(self) -> str | None:
        name = (self.normalized_name or "").strip()
        return name or None

    @model_validator(mode="after")
    def _check(self) -> "ItemUpdateRequest":
        if not self.has_value and self.new_name is None:
            raise ValueError("converted_value, detection_limit, normalized_name 중 하나 이상 보내야 합니다")
        if self.value_source is not None and not self.has_value:
            raise ValueError("value_source 는 값을 입력할 때만 보낼 수 있습니다")
        if not self.has_value:
            return self

        q = self.value_qualifier or (Q.EXACT if self.converted_value is not None else Q.NOT_DETECTED)
        if q in _NUMERIC:
            try:
                self.converted_value = float(self.converted_value)  # "12" 같은 문자열 숫자도 허용
            except (TypeError, ValueError):
                raise ValueError(f"value_qualifier={q} 이면 converted_value 는 숫자여야 합니다") from None
        elif q == Q.NOT_DETECTED:
            if self.converted_value is not None:
                raise ValueError("검출 안 됨(not_detected)이면 converted_value 를 비우고 detection_limit 을 보내야 합니다")
        elif q == Q.TEXT:
            if not isinstance(self.converted_value, str) or not self.converted_value.strip():
                raise ValueError("value_qualifier=text 이면 converted_value 는 문자열이어야 합니다")
        if self.detection_limit is not None and q != Q.NOT_DETECTED:
            raise ValueError("detection_limit 은 검출 안 됨(not_detected) 값에만 보낼 수 있습니다")
        self.value_qualifier = q
        return self

    def to_parsed(self) -> ParsedValue | None:
        """판정 모듈에 넘길 입력값. 값을 보내지 않았으면 None."""
        if not self.has_value:
            return None
        return ParsedValue(self.value_qualifier, self.converted_value, detection_limit=self.detection_limit)


class ReviewLogOut(BaseModel):
    """review_logs 1건 (명세 4.9 응답의 review_logs, 4.10 의 review_log, 4.11 목록)."""
    item_id: str
    action: ReviewAction
    before_value: str | None
    after_value: str | None
    value_source: ValueSource | None = None  # v1.4안. 값 수정(edit)일 때만
    reason: str | None = None                # v1.4. 수정 사유 (확인 이력은 null)
    reviewer_name: str
    reviewed_at: datetime


class ReviewedItem(BaseModel):
    """수정·확인 후의 항목 (명세 4.9 item + v1.4안 reason_code, resolution)."""
    item_id: str
    normalized_name: str
    converted_value: float | str | None
    value_qualifier: Q | None
    detection_limit: float | None = None
    judgement: Judgement
    judgement_reason: str | None
    deviation: float | None
    reason_code: ReasonCode | None = None
    resolution: Resolution | None = None
    reviewed: bool = False
    value_source: ValueSource | None = None


class ItemUpdateResponse(BaseModel):
    """PATCH /documents/{id}/extraction/{item_id} (명세 4.9)."""
    item: ReviewedItem
    lot_recommendation: LotRecommendation
    summary: Summary
    review_logs: list[ReviewLogOut]  # 이번 요청으로 남긴 이력 (항목명 수정 + 값 수정이면 2건)


class ConfirmResponse(BaseModel):
    """POST /documents/{id}/extraction/{item_id}/confirm (명세 4.10)."""
    item: ReviewedItem
    lot_recommendation: LotRecommendation
    summary: Summary
    review_log: ReviewLogOut
