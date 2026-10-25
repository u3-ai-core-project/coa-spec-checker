"""[담당: 장수민] 판정 정책 — 팀 결정에 따라 바뀌는 값을 한곳에 모은다 (명세 v1.4안).

왜 따로 두나
  판정 규칙 중 일부는 팀 회의(멘토님 피드백 반영 범위 확정) 결과에 따라 달라진다.
  규칙 코드를 고치지 않고 설정값만 바꿔 대응할 수 있도록, 규칙은 "사유코드"만 내고
  사유코드 → 판정(5종) 대응은 이 정책 표에서 정한다.

정책 항목 (기본값 = API 명세 v1.4 + 멘토님 「유즈케이스 및 시나리오 범위 정의서」(10.11) 판정표)
  1. 사유코드별 판정 (REASON_JUDGEMENT)
     - 판정 불가(undetermined): 공급사에서 값을 더 받아야 풀리는 경우
     - 확인 필요(check)       : 담당자가 원본·검출한계·항목명을 확인해야 하는 경우
     - 부적합·누락 코드(OUT_OF_SPEC, CONVERTED_OOS, MISSING_REQUIRED)는 판정이 고정이라 바꿀 수 없다
     - SPEC_COPIED·SUM_ONLY 는 확인 필요 (10.25 변경, 이전 기본값은 판정 불가).
       멘토님 판정표·데모 16 "결과 칸 규격 문구 반복 → 확인 필요", 데모 15 "Na+K 합산만 → 조건부 판정/확인".
       기획안 v2 7.1, 가상 CoA 생성기 v2 정답과도 같다.
  2. 검출한계 경계 (ND_LIMIT_INCLUSIVE): 검출한계 == 사내 상한이면 적합인지
  3. 미등록 AI 항목명 (UNMAPPED_AI_ITEM): 기본값 확인 필요 (10.25 변경, 이전 기본값은 참고).
     멘토님 판정표 "항목명 모호·화학종 불명 → 확인 필요, 잘못된 자동 매핑 금지".
     AI 가 추정한 항목명에만 적용되고, 사전으로 매핑한 참고 항목(B, D10 등)은 그대로 참고다.
  4. 교차 규칙 on/off (CROSS_RULES): 중금속 총량 → Pb 등 (안건 5)

정책 값은 app/core/config.py 의 설정(.env)에서 읽는다. 잘못된 값이면 앱 시작 시 ValueError 로 알린다.

※ 정책을 바꾸면 이후 판정부터 적용된다. 이미 저장된 판정 결과는 재판정해야 바뀐다.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType

from app.core.config import Settings, settings as app_settings
from app.core.enums import Judgement, ReasonCode as R


class UnmappedPolicy(StrEnum):
    REFERENCE = "reference"  # 참고 (판정하지 않음, 명세 2.3 현행)
    CHECK = "check"          # 확인 필요 (UNMAPPED_ITEM)


# 판정이 고정인 사유코드. 정책으로 바꿀 수 없다.
FIXED_REASON_JUDGEMENT: Mapping[R, Judgement] = MappingProxyType({
    R.OUT_OF_SPEC: Judgement.FAIL,
    R.CONVERTED_OOS: Judgement.FAIL,
    R.MISSING_REQUIRED: Judgement.MISSING,
})

# 정책으로 바꿀 수 있는 사유코드의 기본 판정 (API 명세 2.3, v1.4안 2.3 기준)
DEFAULT_REASON_JUDGEMENT: Mapping[R, Judgement] = MappingProxyType({
    R.BOUND_ABOVE_LIMIT: Judgement.UNDETERMINED,         # 명세 2.3
    R.SPEC_COPIED: Judgement.CHECK,                      # 멘토님 판정표·데모 16 (10.25 변경, 이전 undetermined)
    R.SUM_ONLY: Judgement.CHECK,                         # 멘토님 데모 15 (10.25 변경, 이전 undetermined)
    R.LOD_ABOVE_LIMIT: Judgement.UNDETERMINED,           # 명세 2.3 표 외 기존 구현
    R.LOWER_LIMIT_UNVERIFIABLE: Judgement.UNDETERMINED,  # 명세 2.3 표 외 기존 구현
    R.ND_NO_LOD: Judgement.CHECK,                        # 명세 2.3
    R.AMBIGUOUS_ANALYTE: Judgement.CHECK,                # v1.4안 (중금속 총량 > Pb 상한)
    R.LOW_CONFIDENCE: Judgement.CHECK,                   # 명세 2.3
    R.UNMAPPED_ITEM: Judgement.CHECK,                    # v1.4안
    R.UNPARSEABLE_VALUE: Judgement.CHECK,                # 명세 2.2
})

# 정책으로 고를 수 있는 판정
_ADJUSTABLE = {Judgement.UNDETERMINED, Judgement.CHECK}


@dataclass(frozen=True)
class JudgementPolicy:
    threshold: float = 0.8
    reason_judgement: Mapping[R, Judgement] = field(default_factory=lambda: dict(DEFAULT_REASON_JUDGEMENT))
    nd_limit_inclusive: bool = True
    unmapped_ai_item: UnmappedPolicy = UnmappedPolicy.CHECK
    cross_rules: tuple[str, ...] = ("heavy_metal_total",)
    heavy_metal_total_name: str = "중금속 총량"
    heavy_metal_target_name: str = "Pb"

    def judgement_for(self, code: R | None) -> Judgement:
        """사유코드 → 판정. 사유코드가 없으면 적합."""
        if code is None:
            return Judgement.PASS
        if code in FIXED_REASON_JUDGEMENT:
            return FIXED_REASON_JUDGEMENT[code]
        return self.reason_judgement.get(code, DEFAULT_REASON_JUDGEMENT[code])

    def with_overrides(self, **changes) -> "JudgementPolicy":
        """일부 값만 바꾼 새 정책 (테스트, 정책 비교 평가용)."""
        return replace(self, **changes)

    @classmethod
    def from_settings(cls, s: Settings | None = None) -> "JudgementPolicy":
        """설정(.env) → 정책. 잘못된 값이면 ValueError."""
        s = s or app_settings
        return cls(
            threshold=s.LOW_CONFIDENCE_THRESHOLD,
            reason_judgement=parse_reason_judgement(s.REASON_JUDGEMENT),
            nd_limit_inclusive=s.ND_LIMIT_INCLUSIVE,
            unmapped_ai_item=_parse_enum(UnmappedPolicy, s.UNMAPPED_AI_ITEM, "UNMAPPED_AI_ITEM"),
            cross_rules=tuple(s.CROSS_RULES),
            heavy_metal_total_name=s.HEAVY_METAL_TOTAL_NAME,
            heavy_metal_target_name=s.HEAVY_METAL_TARGET_NAME,
        )


def parse_reason_judgement(overrides: Mapping[str, str]) -> dict[R, Judgement]:
    """{"SPEC_COPIED": "check"} 같은 설정값을 기본 정책 위에 덮어쓴다."""
    table = dict(DEFAULT_REASON_JUDGEMENT)
    for raw_code, raw_judgement in (overrides or {}).items():
        code = _parse_enum(R, raw_code, "REASON_JUDGEMENT 키")
        judgement = _parse_enum(Judgement, raw_judgement, f"REASON_JUDGEMENT[{raw_code}]")
        if code in FIXED_REASON_JUDGEMENT:
            raise ValueError(f"REASON_JUDGEMENT: {code} 의 판정은 {FIXED_REASON_JUDGEMENT[code]} 로 고정이라 바꿀 수 없습니다")
        if judgement not in _ADJUSTABLE:
            raise ValueError(f"REASON_JUDGEMENT[{code}]: undetermined 또는 check 만 지정할 수 있습니다")
        table[code] = judgement
    return table


def _parse_enum(enum_cls, value, label: str):
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ValueError(f"{label}: '{value}' 는 올바르지 않은 값입니다 (가능: {allowed})") from None


def default_policy() -> JudgementPolicy:
    """현재 설정 기준 정책. 설정을 테스트에서 바꿀 수 있도록 캐시하지 않는다 (생성 비용이 작음)."""
    return JudgementPolicy.from_settings()
