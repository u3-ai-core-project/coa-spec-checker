"""[담당: 장수민] 사유코드별 해결 조건 (명세 v1.4안 2.1 resolution, 기획안 v2 7.2).

멘토님 피드백 ②: 문제 문서는 "확인 필요"로 끝내지 않고 무엇을 확인하면 해결되는지까지 알려준다.
여기서 만드는 resolution 이 그 "해결 조건"이다.
  - condition          : 화면·리포트·문의 초안에 쓰는 문구
  - operator/threshold : 회신값이 조건을 만족하는지 서버가 비교할 때 쓰는 값

자동 재판정
  담당자가 회신값(실측값, 검출한계, 자체 시험값)을 입력하면 검수 API 가 evaluate_item() 을 override 로 다시 호출한다.
  조건을 만족하는 값이면 그 재판정에서 자연히 적합이 되고 reason_code·resolution 이 사라진다.
  그래서 "조건 충족 여부"를 따로 저장하지 않는다.

문구를 바꾸려면 아래 build_resolution() 만 고치면 된다. 공급사 문의 초안(AI 파트)은 이 문구와 수치를 근거로 쓴다.
"""
from app.core.enums import ReasonCode as R, ResolutionType as T
from app.schemas.extraction import Resolution
from app.services.judgement.spec_rule import SpecRule


def fmt_value(v: float | None, unit: str | None) -> str:
    """5 → "5 ppm", 0.4 → "0.4 %". 판정 근거·해결 조건 문구 공용. 값이 없으면 "-"."""
    if v is None:
        return "-"
    s = f"{v:g}"
    return f"{s} {unit}" if unit else s


def _limit(sym: str, v: float | None, unit: str | None, suffix: str = "") -> str:
    """" ≤ 5 ppm" 처럼 비교 문구. 기준값이 없으면 빈 문자열 (규격 범위가 비어 있는 경우 대비)."""
    return f" {sym} {fmt_value(v, unit)}{suffix}" if v is not None else ""


def build_resolution(
    code: R,
    *,
    item_name: str,
    spec: SpecRule | None,
    nd_limit_inclusive: bool = True,
    oxide: str | None = None,
    target_item: str | None = None,
) -> Resolution:
    """사유코드 1개 → 해결 조건 1개.

    item_name   : 이 항목의 사내 표준 항목명
    spec        : 이 항목의 사내 규격 (없을 수 있음: UNMAPPED_ITEM 등)
    target_item : 다른 항목 값을 받아야 할 때 (예: AMBIGUOUS_ANALYTE 는 Pb). 없으면 item_name
    """
    usl = spec.usl if spec else None
    lsl = spec.lsl if spec else None
    unit = spec.unit if spec else None
    target = target_item or item_name

    if code == R.OUT_OF_SPEC:
        return Resolution(type=T.CONFIRM, target_item=target,
                          condition="단위·표기 오류가 아님을 확인 (확인되면 부적합 확정)")
    if code == R.CONVERTED_OOS:
        return Resolution(type=T.CONFIRM, target_item=target,
                          condition=f"{oxide or '산화물'} → {item_name} 환산 결과 확인 (확인되면 부적합 확정)")
    if code == R.BOUND_ABOVE_LIMIT:
        return Resolution(type=T.ACTUAL_VALUE, target_item=target, operator="<=", threshold=usl, unit=unit,
                          condition=f"정량값 또는 상한값{_limit('≤', usl, unit)} 보고")
    if code in (R.ND_NO_LOD, R.LOD_ABOVE_LIMIT):
        op = "<=" if nd_limit_inclusive else "<"
        sym = "≤" if nd_limit_inclusive else "<"
        return Resolution(type=T.DETECTION_LIMIT, target_item=target, operator=op, threshold=usl, unit=unit,
                          condition=f"검출한계{_limit(sym, usl, unit)} (또는 정량값)")
    if code == R.LOWER_LIMIT_UNVERIFIABLE:
        return Resolution(type=T.ACTUAL_VALUE, target_item=target, operator=">=", threshold=lsl, unit=unit,
                          condition=f"정량값 (사내 하한{_limit('≥', lsl, unit)} 확인용)")
    if code == R.SPEC_COPIED:
        return Resolution(type=T.ACTUAL_VALUE, target_item=target,
                          condition="실측값이 적힌 CoA (결과 칸에 규격 문구가 적힘)")
    if code == R.MISSING_REQUIRED:
        return Resolution(type=T.INTERNAL_TEST, target_item=target,
                          condition="별도 성적서 값 또는 자체 시험값 입력")
    if code == R.AMBIGUOUS_ANALYTE:
        return Resolution(type=T.SINGLE_VALUE, target_item=target, operator="<=", threshold=usl, unit=unit,
                          condition=f"{target} 단일 분석값{_limit('≤', usl, unit)}")
    if code == R.SUM_ONLY:
        return Resolution(type=T.SINGLE_VALUE, target_item=target, condition=f"{target} 개별값")
    if code == R.LOW_CONFIDENCE:
        return Resolution(type=T.CONFIRM, target_item=target, condition="원문 하이라이트와 대조해 값 확인")
    if code == R.UNMAPPED_ITEM:
        return Resolution(type=T.CONFIRM, target_item=target,
                          condition="사내 표준 항목명으로 수정하거나 참고 항목으로 확인")
    if code == R.UNPARSEABLE_VALUE:
        return Resolution(type=T.CONFIRM, target_item=target, condition="원문 값을 확인해 수치로 입력")
    raise ValueError(f"해결 조건이 정의되지 않은 사유코드: {code}")
