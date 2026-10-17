"""[담당: 장수민] 교차 규칙 — 여러 항목을 함께 봐야 판정할 수 있는 규칙 (명세 v1.4안 2.3, 기획안 v2 7.1).

항목 판정(item_judge.evaluate_item)은 항목을 하나씩 본다. 아래 규칙은 그 결과 목록 전체를 받아
일부 항목의 판정을 다시 정한다. 문서 판정(engine.judge_document)과 재계산(engine.refresh_summary) 때 실행한다.

규칙 켜고 끄기: 설정 CROSS_RULES (policy.cross_rules). 아래 CROSS_RULES 표에 등록된 이름만 쓸 수 있다.

규칙 작성 원칙
  - 같은 입력이면 몇 번을 다시 돌려도 결과가 같아야 한다 (재계산 때마다 실행되므로).
    그래서 규칙이 바꾼 항목은 "규칙이 적용되지 않을 때의 판정"으로 되돌릴 수 있어야 한다.
  - 담당자가 직접 입력한 값(override)이 있는 항목은 건드리지 않는다.
  - 숫자를 임의로 나누거나 추정하지 않는다 (보수적으로 성립하는 경우만 적합).

새 규칙 추가 방법 (예: Na+K 합산, SUM_ONLY)
  1. def na_k_sum(items, specs, policy) -> list[ExtractionItem] 작성
  2. 아래 CROSS_RULES 에 "na_k_sum": na_k_sum 등록
  3. 설정 CROSS_RULES 에 이름 추가
  ※ Na+K 합산 규칙은 팀 결정(안건 5) 전이라 등록하지 않았다. 판정은 policy 의 SUM_ONLY 가 이미 정의돼 있다.
"""
from collections.abc import Callable, Mapping

from app.core.enums import MappingSource, ReasonCode as R, ValueQualifier as Q
from app.schemas.extraction import ExtractedItem, ExtractionItem
from app.services.judgement.policy import JudgementPolicy
from app.services.judgement.resolutions import build_resolution, fmt_value
from app.services.judgement.spec_rule import SpecRule, name_key
from app.services.judgement.value_parser import convert_unit, parse_value, UnitConversionError

CrossRule = Callable[[list[ExtractionItem], Mapping[str, SpecRule], JudgementPolicy], list[ExtractionItem]]


# ---------------------------------------------------------------------------
# 중금속 총량 → Pb (v1.4안 2.3)
# ---------------------------------------------------------------------------
def heavy_metal_total(
    items: list[ExtractionItem], specs: Mapping[str, SpecRule], policy: JudgementPolicy
) -> list[ExtractionItem]:
    """CoA 에 Pb 단일값이 없고 "Heavy metals (as Pb)" 같은 중금속 총량만 있을 때 Pb 를 판정한다.

      총량 ≤ Pb 사내 상한 → Pb 적합   (Pb ≤ 총량 이므로 보수적으로 성립)
      총량 > Pb 사내 상한 → AMBIGUOUS_ANALYTE (기본: 확인 필요, Pb 단일값 요청)

    적용하지 않는 경우 (Pb 는 원래 판정 그대로, 보통 누락)
      - Pb 사내 규격(상한)이 없음
      - Pb 단일값이 CoA 에 있음, 또는 담당자가 Pb 값을 입력함
      - 총량 항목이 없음, 또는 총량 값 자체가 예외(신뢰도 낮음, 규격 복사, 검출한계 미기재 등)
    """
    target_key = name_key(policy.heavy_metal_target_name)
    total_key = name_key(policy.heavy_metal_total_name)
    target_spec = specs.get(target_key)
    if target_spec is None or target_spec.usl is None:
        return items

    idx = next((n for n, i in enumerate(items) if name_key(i.normalized_name) == target_key), None)
    if idx is None:
        return items  # Pb 가 필수가 아니어서 누락 항목도 없는 경우
    target = items[idx]
    # Pb 실측값이 있거나(CoA 에 있음) 담당자가 값을 넣었으면 규칙 대상이 아니다
    if (target.mapping_source != MappingSource.SPEC or target.value_source is not None
            or target.converted_value is not None):
        return items

    bound = _total_upper_bound(items, total_key, specs, target_spec, policy)
    out = list(items)
    if bound is None:
        out[idx] = _as_missing(target, target_spec, policy)  # 규칙 미적용 → 누락으로 (재계산 시 되돌리기)
        return out

    value, unit = bound, target_spec.unit
    usl = target_spec.usl
    if value <= usl:
        out[idx] = target.model_copy(update={
            "judgement": policy.judgement_for(None),
            "judgement_reason": f"{policy.heavy_metal_total_name} {fmt_value(value, unit)} ≤ "
                                f"{target.normalized_name} 사내 상한 {fmt_value(usl, unit)} (총량 ≥ 개별값이므로 적합)",
            "reason_code": None,
            "resolution": None,
            "deviation": None,
        })
    else:
        out[idx] = target.model_copy(update={
            "judgement": policy.judgement_for(R.AMBIGUOUS_ANALYTE),
            "judgement_reason": f"{policy.heavy_metal_total_name} {fmt_value(value, unit)} > "
                                f"{target.normalized_name} 사내 상한 {fmt_value(usl, unit)}, "
                                f"{target.normalized_name} 단일값을 알 수 없음",
            "reason_code": R.AMBIGUOUS_ANALYTE,
            "resolution": build_resolution(R.AMBIGUOUS_ANALYTE, item_name=target.normalized_name, spec=target_spec,
                                           target_item=target.normalized_name),
            "deviation": None,
        })
    return out


def _total_upper_bound(
    items: list[ExtractionItem], total_key: str, specs: Mapping[str, SpecRule],
    target_spec: SpecRule, policy: JudgementPolicy,
) -> float | None:
    """중금속 총량의 상한(대상 항목 단위). 쓸 수 없으면 None.

    총량 항목에 사내 규격이 있으면(범위 없음, is_required=False 로 등록 권장) 항목 판정에서 신뢰도·규격 복사·
    검출한계 검사를 이미 거쳤으므로 reason_code 가 없을 때만 converted_value 를 쓴다.
    규격이 없으면 원문 값을 직접 해석하고, 신뢰도 기준값 미만이면 쓰지 않는다.
    """
    total = next((i for i in items if name_key(i.normalized_name) == total_key
                  and i.mapping_source != MappingSource.SPEC), None)
    if total is None or total.reason_code is not None:
        return None

    total_spec = specs.get(total_key)
    if total_spec is not None and total_spec.is_quantitative:
        qualifier, value, dl, unit = total.value_qualifier, total.converted_value, total.detection_limit, total_spec.unit
    else:
        if total.confidence is not None and total.confidence < policy.threshold:
            return None
        parsed = parse_value(total.raw_value, unit=total.unit, target_unit=target_spec.unit)
        if parsed.error:
            return None
        qualifier, value, dl, unit = parsed.qualifier, parsed.value, parsed.detection_limit, target_spec.unit

    if qualifier in (Q.EXACT, Q.LESS_THAN, Q.LESS_EQUAL):
        bound = value
    elif qualifier == Q.NOT_DETECTED:
        bound = dl  # 검출 안 됨이면 검출한계가 상한
    else:
        return None
    if not isinstance(bound, (int, float)):
        return None
    try:
        return convert_unit(float(bound), unit, target_spec.unit)
    except UnitConversionError:
        return None


def _as_missing(target: ExtractionItem, spec: SpecRule, policy: JudgementPolicy) -> ExtractionItem:
    """규칙이 적용되지 않을 때의 판정(누락)으로 되돌린다."""
    from app.services.judgement.item_judge import evaluate_item  # 순환 import 방지
    base = ExtractedItem.model_validate(target.model_dump(include=set(ExtractedItem.model_fields)))
    return evaluate_item(base, spec, policy=policy)


# ---------------------------------------------------------------------------
# 등록표
# ---------------------------------------------------------------------------
CROSS_RULES: dict[str, CrossRule] = {
    "heavy_metal_total": heavy_metal_total,
    # "na_k_sum": na_k_sum,  # 안건 5 결정 후 추가
}


def validate_rule_names(names: tuple[str, ...]) -> None:
    unknown = [n for n in names if n not in CROSS_RULES]
    if unknown:
        raise ValueError(f"CROSS_RULES: 등록되지 않은 규칙 {unknown} (가능: {list(CROSS_RULES)})")


def apply_cross_rules(
    items: list[ExtractionItem], specs: Mapping[str, SpecRule], policy: JudgementPolicy
) -> list[ExtractionItem]:
    """정책에서 켠 규칙을 순서대로 적용한다. specs 는 name_key(항목명) → SpecRule."""
    validate_rule_names(policy.cross_rules)
    for name in policy.cross_rules:
        items = CROSS_RULES[name](items, specs, policy)
    return items
