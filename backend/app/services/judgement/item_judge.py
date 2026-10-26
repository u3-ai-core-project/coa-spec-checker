"""[담당: 장수민] 항목 판정 — 사유코드, 판정 5종, 해결 조건, deviation, judgement_reason (명세 2.3, v1.4안).

구조 (v1.4안)
  규칙은 "왜 문제인가"를 사유코드(reason_code)로 내고, 판정(judgement)은 정책 표(policy.py)가 사유코드에서 정한다.
  사유코드가 없으면 적합(pass). 예외 항목에는 해결 조건(resolution)을 함께 붙인다.

판정 순서 (위에서 먼저 걸리는 것으로 끝)
  1. 사내 규격 없음              → 참고(pass). 단, 정책이 check 이고 AI 추정 항목명이면 UNMAPPED_ITEM
  2. 누락 항목(mapping_source=spec, 입력값 없음) → MISSING_REQUIRED (누락). 필수 정성 항목도 같다 (10.25)
     정성 항목(값이 있음)         → 참고(pass)
  3. 신뢰도 기준값 미만 (검수 전) → LOW_CONFIDENCE   ※ 값 판정보다 우선
  4. 결과 칸 = 규격 문구 (검수 전) → SPEC_COPIED
  5. 값 해석 실패                → UNPARSEABLE_VALUE
  6. 값 판정 (judge_value)       → OUT_OF_SPEC / CONVERTED_OOS / BOUND_ABOVE_LIMIT / ND_NO_LOD / ...

재판정 (명세 2.3 아래, 4.9, 4.10)
  - 값 확인(confirm)        : reviewed=True → 3 을 건너뛰고 원문 값으로 다시 판정
  - 값 수정(edit)·회신값·자체 시험 : override=ParsedValue(...) → 3, 4, 5 를 건너뛰고 입력값으로 판정
      검출한계 회신은 override=ParsedValue(NOT_DETECTED, None, detection_limit=x)
  - 항목명 수정(rename)     : 새 항목명의 SpecRule 로 다시 호출
  재판정에서 해결 조건을 만족하면 적합이 되고 reason_code·resolution 은 비워진다 (resolutions.py 참고).

여러 항목을 함께 봐야 하는 규칙(중금속 총량 → Pb 등)은 cross_rules.py 에서 이 판정 뒤에 적용한다.
"""
from dataclasses import dataclass

from app.core.enums import MappingSource, ReasonCode as R, ValueQualifier as Q, ValueSource
from app.schemas.extraction import ExtractedItem, ExtractionItem
from app.services.judgement.policy import JudgementPolicy, UnmappedPolicy, default_policy
from app.services.judgement.resolutions import build_resolution, fmt_value as _fmt
from app.services.judgement.spec_rule import SpecRule
from app.services.judgement.value_parser import ParsedValue, is_spec_text_as_result, parse_value

REASON_NO_SPEC = "규격 없음"
REASON_QUALITATIVE = "정성 항목, 판정 제외"
REASON_NO_RANGE = "사내 규격 범위 미설정"
REASON_MISSING = "CoA에 항목 없음"
REASON_SPEC_TEXT = "결과 칸이 규격 문구와 같음"
REASON_NO_DL = "검출한계 미기재"
REASON_UNMAPPED = "사내 규격에 없는 항목명 (AI 추정)"


@dataclass(frozen=True)
class Verdict:
    """규칙 1개의 결과. code 가 없으면 적합."""
    code: R | None = None
    reason: str | None = None
    deviation: float | None = None


def judge_value(parsed: ParsedValue, spec: SpecRule, *, nd_limit_inclusive: bool = True) -> Verdict:
    """해석된 값 하나를 정량 규격과 비교한다 (명세 2.3 의 값 판정 부분).

    nd_limit_inclusive: 검출 안 됨에서 검출한계 == 사내 상한을 적합으로 볼지 (정책 ND_LIMIT_INCLUSIVE)
    """
    lsl, usl, unit = spec.lsl, spec.usl, spec.unit

    if parsed.error:
        return Verdict(R.UNPARSEABLE_VALUE, parsed.error)

    if parsed.qualifier == Q.TEXT:
        return Verdict(R.UNPARSEABLE_VALUE, "정량 항목인데 값이 문자열")

    if lsl is None and usl is None:
        return Verdict(None, REASON_NO_RANGE)

    if parsed.qualifier == Q.EXACT:
        v = float(parsed.value)
        # 산화물 환산을 거친 값이면 CONVERTED_OOS 로 구분 (환산식 확인이 해결 조건)
        code = R.CONVERTED_OOS if parsed.oxide else R.OUT_OF_SPEC
        via = f" ({parsed.oxide} 환산)" if parsed.oxide else ""
        if usl is not None and v > usl:
            return Verdict(code, f"사내 상한 {_fmt(usl, unit)} 초과{via}", float(f"{v - usl:.12g}"))
        if lsl is not None and v < lsl:
            return Verdict(code, f"사내 하한 {_fmt(lsl, unit)} 미만{via}", float(f"{v - lsl:.12g}"))
        return Verdict(None)

    if parsed.qualifier in (Q.LESS_THAN, Q.LESS_EQUAL):
        sym = "<" if parsed.qualifier == Q.LESS_THAN else "≤"
        shown = f"상한값만 기재됨({sym} {_fmt(parsed.value, unit)})"
        if lsl is not None:
            return Verdict(R.LOWER_LIMIT_UNVERIFIABLE, f"{shown}, 사내 하한 충족 여부 확인 불가")
        if parsed.value <= usl:
            return Verdict(None, f"{shown}, 사내 상한 {_fmt(usl, unit)} 이하")
        return Verdict(R.BOUND_ABOVE_LIMIT, f"{shown}, 사내 상한 {_fmt(usl, unit)}보다 큼")

    if parsed.qualifier == Q.NOT_DETECTED:
        dl = parsed.detection_limit
        if dl is None:
            return Verdict(R.ND_NO_LOD, REASON_NO_DL)
        if lsl is not None:
            return Verdict(R.LOWER_LIMIT_UNVERIFIABLE, f"검출 안 됨(검출한계 {_fmt(dl, unit)}), 사내 하한이 있는 항목")
        if dl < usl or (nd_limit_inclusive and dl == usl):
            return Verdict(None, f"검출 안 됨(검출한계 {_fmt(dl, unit)})")
        if dl == usl:
            return Verdict(R.LOD_ABOVE_LIMIT, f"검출한계 {_fmt(dl, unit)}가 사내 상한과 같음 (경계 미포함 정책)")
        return Verdict(R.LOD_ABOVE_LIMIT, f"검출한계 {_fmt(dl, unit)}가 사내 상한 {_fmt(usl, unit)}보다 큼")

    return Verdict(R.UNPARSEABLE_VALUE, "값 형식을 해석할 수 없음")


def evaluate_item(
    item: ExtractedItem,
    spec: SpecRule | None,
    *,
    threshold: float | None = None,
    reviewed: bool = False,
    override: ParsedValue | None = None,
    oxide_factors: dict[str, float] | None = None,
    policy: JudgementPolicy | None = None,
    value_source: ValueSource | None = None,
) -> ExtractionItem:
    """항목 1개를 판정해 서버 필드까지 채운 새 ExtractionItem 을 돌려준다. 입력은 바꾸지 않는다.

    item      : AI 추출 항목(ExtractedItem) 또는 이미 저장된 항목(ExtractionItem)
    spec      : 이 항목의 사내 규격. 없으면 None
    threshold : 신뢰도 기준값. None 이면 정책 값 (기존 호출 호환용으로 남겨 둠)
    reviewed  : 담당자가 확인(confirm) 또는 수정(edit)한 항목이면 True
    override  : 담당자가 입력한 값 (값 수정, 회신값, 자체 시험 값)
    policy    : 판정 정책. None 이면 현재 설정 기준 (policy.default_policy)
    value_source : override 값의 출처 (원문 오독 수정 / 공급사 회신 / 자체 시험). override 가 있을 때만 의미 있음

    결과 항목의 reviewed·value_source 에 검수 상태를 남긴다 (rejudge_item 이 이 값으로 다시 판정한다).
    """
    policy = policy or default_policy()
    threshold = policy.threshold if threshold is None else threshold
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
        resolution = None
        if v.code is not None:
            resolution = build_resolution(
                v.code, item_name=item.normalized_name, spec=spec,
                nd_limit_inclusive=policy.nd_limit_inclusive, oxide=parsed.oxide if parsed else None,
            )
        return ExtractionItem(
            **base,
            value_qualifier=parsed.qualifier if parsed else None,
            converted_value=parsed.value if parsed else None,
            detection_limit=parsed.detection_limit if parsed else None,
            spec_lsl=spec.lsl if spec else None,
            spec_usl=spec.usl if spec else None,
            judgement=policy.judgement_for(v.code),
            judgement_reason=v.reason,
            deviation=v.deviation,
            reason_code=v.code,
            resolution=resolution,
            reviewed=reviewed or override is not None,
            value_source=(value_source or ValueSource.CORRECTION) if override is not None else None,
        )

    # 1. 판정하지 않는 항목
    if spec is None:
        # 정책(안건 3): AI 가 추정한 항목명이 규격과 맞지 않으면 확인 필요로 올릴 수 있다.
        # 사전(dictionary)으로 매핑했는데 규격에 없는 항목은 원래 참고 항목(B, D10 등)이므로 그대로 둔다.
        if policy.unmapped_ai_item == UnmappedPolicy.CHECK and item.mapping_source == MappingSource.AI:
            return build(Verdict(R.UNMAPPED_ITEM, REASON_UNMAPPED))
        return build(Verdict(None, REASON_NO_SPEC))

    # 2. 누락. 정성 항목보다 먼저 본다: 필수 정성 항목(예: 외관)이 CoA 에 없으면 참고가 아니라 누락이다
    #    (멘토님 범위 정의서 E06 "필수항목 미검사 → 보류"). 값이 있는 정성 항목은 아래에서 참고로 처리한다.
    if parsed is None:
        return build(Verdict(R.MISSING_REQUIRED, REASON_MISSING))
    if not spec.is_quantitative:
        return build(Verdict(None, REASON_QUALITATIVE))

    if override is None:
        # 3. 신뢰도 낮음 (값 판정보다 우선)
        if not reviewed and item.confidence is not None and item.confidence < threshold:
            return build(Verdict(R.LOW_CONFIDENCE, f"추출 신뢰도 낮음({item.confidence:.2f})"))
        # 4. 결과 칸 = 규격 문구
        if is_spec_text_as_result(item.raw_value, item.raw_spec):
            return build(Verdict(R.SPEC_COPIED, REASON_SPEC_TEXT))

    # 5, 6. 값 판정
    return build(judge_value(parsed, spec, nd_limit_inclusive=policy.nd_limit_inclusive))


def current_override(item: ExtractionItem) -> ParsedValue | None:
    """담당자가 입력해 둔 값이 있으면 그 값을 ParsedValue 로 돌려준다 (없으면 None)."""
    if item.value_source is None:
        return None
    return ParsedValue(item.value_qualifier, item.converted_value, detection_limit=item.detection_limit)


def rejudge_item(
    item: ExtractionItem,
    spec: SpecRule | None,
    *,
    policy: JudgementPolicy | None = None,
    oxide_factors: dict[str, float] | None = None,
) -> ExtractionItem:
    """저장된 항목을 담당자 검수 상태를 유지한 채 다시 판정한다.

    항목명 수정(새 규격으로 판정), 규격 개정 재판정(S6), 정책 변경 후 재판정에 쓴다.
      - 담당자가 값을 입력한 항목 → 그 값(override)으로
      - 담당자가 확인만 한 항목   → 신뢰도 조건 없이 원문 값으로 (reviewed=True)
      - 그 외                     → 처음 판정과 같은 방식으로
    ※ 입력값(converted_value)은 입력 당시 규격 단위 기준이다. 단위가 다른 규격으로 바꾸면 값을 다시 입력해야 한다.
    """
    return evaluate_item(
        item, spec,
        reviewed=item.reviewed,
        override=current_override(item),
        value_source=item.value_source,
        policy=policy,
        oxide_factors=oxide_factors,
    )
