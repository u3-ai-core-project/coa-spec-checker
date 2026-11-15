"""[담당: 장수민] 값 해석: raw_value → value_qualifier, converted_value, detection_limit (명세 2.2).

DB 를 쓰지 않는 순수 함수. 해석에 실패하면 예외 대신 ParsedValue.error 에 사유를 담아 돌려주고,
item_judge 가 이를 확인 필요(check) 로 판정한다.

※ 업무 분담 문서에는 값 해석을 AI 추출 파트가 한다고 되어 있고, 명세 2.1 은 서버가 채운다고 되어 있다.
  담당이 정해질 때까지 서버 쪽 구현을 기준으로 둔다.
"""
import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.enums import ValueQualifier

# ---------------------------------------------------------------------------
# 단위
# ---------------------------------------------------------------------------
# 질량 분율 단위 → ppm 배수. 1 % = 10,000 ppm
_TO_PPM = {
    "%": 10_000.0,
    "ppm": 1.0,
    "mg/kg": 1.0,
    "ug/g": 1.0,
    "ppb": 0.001,
    "ug/kg": 0.001,
    "g/kg": 1_000.0,
}
_UNIT_ALIASES = {"wt%": "%", "w/w%": "%", "%w/w": "%", "mass%": "%", "μg/g": "ug/g", "µg/g": "ug/g"}


class UnitConversionError(ValueError):
    pass


def ppm_factors() -> dict[str, float]:
    """단위 → ppm 배수표 사본 (GET /mappings/conversions 조회용). 판정은 convert_unit() 이 이 표를 쓴다."""
    return dict(_TO_PPM)


def normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.strip().lower().replace(" ", "").replace("μ", "u").replace("µ", "u")
    if not u:
        return None
    return _UNIT_ALIASES.get(u, u)


def convert_unit(value: float, from_unit: str | None, to_unit: str | None) -> float:
    """from_unit → to_unit. 어느 한쪽이 없거나 같으면 그대로 둔다."""
    f, t = normalize_unit(from_unit), normalize_unit(to_unit)
    if f is None or t is None or f == t:
        return value
    if f in _TO_PPM and t in _TO_PPM:
        return _clean(value * _TO_PPM[f] / _TO_PPM[t])
    raise UnitConversionError(f"단위 환산 불가({from_unit} → {to_unit})")


# ---------------------------------------------------------------------------
# 산화물 → 원소
# ---------------------------------------------------------------------------
_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def find_oxide(raw_name: str | None, factors: dict[str, float] | None = None) -> tuple[str | None, float]:
    """raw_name 에 Na2O, CaO, Fe2O3 같은 산화물 표기가 있으면 (화학식, 원소 환산 계수), 없으면 (None, 1)."""
    if not raw_name:
        return None, 1.0
    factors = settings.OXIDE_TO_ELEMENT if factors is None else factors
    name = raw_name.translate(_SUBSCRIPTS)
    for formula, factor in factors.items():
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(formula)}(?![a-z0-9])", name):
            return formula, factor
    return None, 1.0


def oxide_element(formula: str) -> str | None:
    """산화물 화학식의 원소 기호 (맨 앞 원소). "Na2O" → "Na", "Fe2O3" → "Fe". 읽을 수 없으면 None."""
    m = re.match(r"[A-Z][a-z]?", formula.translate(_SUBSCRIPTS).strip())
    return m.group(0) if m else None


def oxide_factor(raw_name: str | None, factors: dict[str, float] | None = None) -> float:
    """원소 환산 계수만 필요할 때 (산화물 표기가 없으면 1)."""
    return find_oxide(raw_name, factors)[1]


# ---------------------------------------------------------------------------
# 값 해석
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParsedValue:
    qualifier: ValueQualifier | None
    value: float | str | None
    detection_limit: float | None = None
    error: str | None = None  # 해석 실패 사유. 있으면 판정은 check
    oxide: str | None = None  # 산화물 환산을 했으면 원래 화학식 (예: "Na2O"). 부적합이면 CONVERTED_OOS 로 구분


_ND = re.compile(
    r"(?<![a-z])n\.?\s?d\.?(?![a-z])|none\s+detected|not\s+detected|검출\s*안\s*됨|검출되지\s*않|불검출|미검출",
    re.IGNORECASE,
)
_NUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_UNIT = r"[%A-Za-zμµ][%A-Za-zμµ/]*"  # %, ppm, wt%, mg/kg, μg/g ...
_VALUE = re.compile(rf"^(?P<op><=|>=|<|>)?\s*(?P<num>{_NUM})\s*(?P<unit>{_UNIT})?$")


def _normalize_text(s: str) -> str:
    s = s.strip()
    s = (s.replace("＜", "<").replace("＞", ">").replace("≦", "<=").replace("≤", "<=")
          .replace("≧", ">=").replace("≥", ">=").replace("=<", "<=").replace("=>", ">="))
    s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)      # 천 단위 쉼표 1,000 → 1000
    s = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", s)   # 소수점 쉼표 0,5 → 0.5
    return s


def _clean(x: float) -> float:
    """0.002 * 10000 = 20.000000000000004 같은 부동소수 오차 정리."""
    return float(f"{x:.12g}")


def parse_value(
    raw_value: str | None,
    *,
    unit: str | None = None,
    target_unit: str | None = None,
    raw_name: str | None = None,
    oxide_factors: dict[str, float] | None = None,
) -> ParsedValue:
    """CoA 원문 값을 사내 규격 단위(target_unit) 기준으로 해석한다.

    unit       : AI 가 따로 추출한 단위. 값 안에 단위가 있으면("0.002 %") 그쪽을 우선한다.
    raw_name   : 산화물 표기 확인용 (Na2O → Na 환산).
    """
    if raw_value is None or not raw_value.strip():
        return ParsedValue(None, None, error="값 없음")

    s = _normalize_text(raw_value)
    oxide, factor = find_oxide(raw_name, oxide_factors)

    def to_target(num: float, value_unit: str | None) -> float:
        return _clean(convert_unit(num, value_unit or unit, target_unit) * factor)

    try:
        # 검출 안 됨. 같이 적힌 숫자는 검출한계로 본다 ("ND (<0.5 ppm)", "N.D.(DL 0.0001%)")
        if _ND.search(s):
            rest = _ND.sub(" ", s)
            m = re.search(rf"(?P<num>{_NUM})\s*(?P<unit>{_UNIT})?", rest)
            dl = to_target(float(m["num"]), m["unit"]) if m else None
            return ParsedValue(ValueQualifier.NOT_DETECTED, None, detection_limit=dl, oxide=oxide if dl else None)

        m = _VALUE.match(s)
        if m is None:
            if not re.search(r"\d", s):
                return ParsedValue(ValueQualifier.TEXT, raw_value.strip())
            return ParsedValue(None, None, error=f"값 형식을 해석할 수 없음({raw_value.strip()})")

        op = m["op"]
        if op in (">", ">="):
            return ParsedValue(None, None, error=f"하한 표기({op})는 판정 규칙에 없음")

        value = to_target(float(m["num"]), m["unit"])
        qualifier = {
            None: ValueQualifier.EXACT,
            "<": ValueQualifier.LESS_THAN,
            "<=": ValueQualifier.LESS_EQUAL,
        }[op]
        return ParsedValue(qualifier, value, oxide=oxide)

    except UnitConversionError as e:
        return ParsedValue(None, None, error=str(e))


# ---------------------------------------------------------------------------
# 결과 칸 = 규격 문구
# ---------------------------------------------------------------------------
def _spec_key(s: str) -> str:
    return re.sub(r"\s+", "", _normalize_text(s)).casefold()


def is_spec_text_as_result(raw_value: str | None, raw_spec: str | None) -> bool:
    """결과 칸에 규격 문구를 그대로 적었는지 ("≤ 0.01%" vs "=<0.01 %" 는 같은 것으로 본다)."""
    if not raw_value or not raw_spec:
        return False
    return _spec_key(raw_value) == _spec_key(raw_spec)
