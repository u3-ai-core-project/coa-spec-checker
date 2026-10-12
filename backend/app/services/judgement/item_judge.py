"""[담당: 장수민] 항목 판정 5종, deviation, judgement_reason (명세 2.3).

판정 우선순위
  1. 사내 규격 없음 / 정성 항목   → pass (참고, 판정하지 않음)
  2. 누락 항목(mapping_source=spec, 입력값 없음) → missing
  3. 신뢰도 기준값 미만 (검수 전)  → check   ※ 값 판정보다 우선
  4. 결과 칸 = 규격 문구 (검수 전) → undetermined
  5. 값 해석 실패                 → check
  6. 값 판정 (exact / less_than·less_equal / not_detected / text)

재판정 (명세 2.3 아래, 4.9, 4.10)
  - 값 확인(confirm)        : reviewed=True → 3 을 건너뛰고 원문 값으로 다시 판정
  - 값 수정(edit)·자체 시험 : override=ParsedValue(...) → 3, 4, 5 를 건너뛰고 입력값으로 판정
  - 항목명 수정(rename)     : 새 항목명의 SpecRule 로 다시 호출
"""
from dataclasses import dataclass

from app.core.enums import Judgement, MappingSource, ValueQualifier as Q
from app.schemas.extraction import ExtractedItem, ExtractionItem
from app.services.judgement.spec_rule import SpecRule
from app.services.judgement.value_parser import ParsedValue, is_spec_text_as_result, parse_value

REASON_NO_SPEC = "규격 없음"
REASON_QUALITATIVE = "정성 항목, 판정 제외"
REASON_NO_RANGE = "사내 규격 범위 미설정"
REASON_MISSING = "CoA에 항목 없음"
REASON_SPEC_TEXT = "결과 칸이 규격 문구와 같음"
REASON_NO_DL = "검출한계 미기재"


@dataclass(frozen=True)
class Verdict:
    judgement: Judgement
    reason: str | None = None
    deviation: float | None = None


def _fmt(v: float | None, unit: str | None) -> str:
    s = f"{v:g}"
    return f"{s} {unit}" if unit else s


def judge_value(parsed: ParsedValue, spec: SpecRule) -> Verdict:
    """해석된 값 하나를 정량 규격과 비교한다 (명세 2.3 의 값 판정 부분)."""
    lsl, usl, unit = spec.lsl, spec.usl, spec.unit

    if parsed.error:
        return Verdict(Judgement.CHECK, parsed.error)

    if parsed.qualifier == Q.TEXT:
        return Verdict(Judgement.CHECK, "정량 항목인데 값이 문자열")

    if lsl is None and usl is None:
        return Verdict(Judgement.PASS, REASON_NO_RANGE)

    if parsed.qualifier == Q.EXACT:
        v = float(parsed.value)
        if usl is not None and v > usl:
            return Verdict(Judgement.FAIL, f"사내 상한 {_fmt(usl, unit)} 초과", float(f"{v - usl:.12g}"))
        if lsl is not None and v < lsl:
            return Verdict(Judgement.FAIL, f"사내 하한 {_fmt(lsl, unit)} 미만", float(f"{v - lsl:.12g}"))
        return Verdict(Judgement.PASS)

    if parsed.qualifier in (Q.LESS_THAN, Q.LESS_EQUAL):
        sym = "<" if parsed.qualifier == Q.LESS_THAN else "≤"
        shown = f"상한값만 기재됨({sym} {_fmt(parsed.value, unit)})"
        if lsl is not None:
            return Verdict(Judgement.UNDETERMINED, f"{shown}, 사내 하한 충족 여부 확인 불가")
        if parsed.value <= usl:
            return Verdict(Judgement.PASS, f"{shown}, 사내 상한 {_fmt(usl, unit)} 이하")
        return Verdict(Judgement.UNDETERMINED, f"{shown}, 사내 상한 {_fmt(usl, unit)}보다 큼")

    if parsed.qualifier == Q.NOT_DETECTED:
        dl = parsed.detection_limit
        if dl is None:
            return Verdict(Judgement.CHECK, REASON_NO_DL)
        if lsl is not None:
            return Verdict(Judgement.CHECK, f"검출 안 됨(검출한계 {_fmt(dl, unit)}), 사내 하한이 있는 항목")
        if dl <= usl:
            return Verdict(Judgement.PASS, f"검출 안 됨(검출한계 {_fmt(dl, unit)})")
        return Verdict(Judgement.UNDETERMINED, f"검출한계 {_fmt(dl, unit)}가 사내 상한 {_fmt(usl, unit)}보다 큼")

    return Verdict(Judgement.CHECK, "값 형식을 해석할 수 없음")


def evaluate_item(
    item: ExtractedItem,
    spec: SpecRule | None,
    *,
    threshold: float,
    reviewed: bool = False,
    override: ParsedValue | None = None,
    oxide_factors: dict[str, float] | None = None,
) -> ExtractionItem:
    """항목 1개를 판정해 서버 필드까지 채운 새 ExtractionItem 을 돌려준다. 입력은 바꾸지 않는다.

    item     : AI 추출 항목(ExtractedItem) 또는 이미 저장된 항목(ExtractionItem)
    spec     : 이 항목의 사내 규격. 없으면 None
    reviewed : 담당자가 확인(confirm) 또는 수정(edit)한 항목이면 True
    override : 담당자가 입력한 값 (값 수정, 자체 시험 값)
    """
    base = item.model_dump(include=set(ExtractedItem.model_fields))
    target_unit = spec.unit if spec else None

    if override is not None:
        parsed = override
    elif item.raw_value is None and item.mapping_source == MappingSource.SPEC:
        parsed = None  # 누락 항목
    else:
        parsed = parse_value(item.raw_value, unit=item.unit, target_unit=target_unit,
                             raw_name=item.raw_name, oxide_factors=oxide_factors)

    def build(v: Verdict) -> ExtractionItem:
        return ExtractionItem(
            **base,
            value_qualifier=parsed.qualifier if parsed else None,
            converted_value=parsed.value if parsed else None,
            detection_limit=parsed.detection_limit if parsed else None,
            spec_lsl=spec.lsl if spec else None,
            spec_usl=spec.usl if spec else None,
            judgement=v.judgement,
            judgement_reason=v.reason,
            deviation=v.deviation,
        )

    # 1. 판정하지 않는 항목
    if spec is None:
        return build(Verdict(Judgement.PASS, REASON_NO_SPEC))
    if not spec.is_quantitative:
        return build(Verdict(Judgement.PASS, REASON_QUALITATIVE))

    # 2. 누락
    if parsed is None:
        return build(Verdict(Judgement.MISSING, REASON_MISSING))

    if override is None:
        # 3. 신뢰도 낮음 (값 판정보다 우선)
        if not reviewed and item.confidence is not None and item.confidence < threshold:
            return build(Verdict(Judgement.CHECK, f"추출 신뢰도 낮음({item.confidence:.2f})"))
        # 4. 결과 칸 = 규격 문구
        if is_spec_text_as_result(item.raw_value, item.raw_spec):
            return build(Verdict(Judgement.UNDETERMINED, REASON_SPEC_TEXT))

    # 5, 6. 값 판정
    return build(judge_value(parsed, spec))
