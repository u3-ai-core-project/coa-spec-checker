"""[담당: 장수민] 판정에 쓰는 사내 규격 1건.

판정 모듈이 DB 모델(SpecItem)에 의존하지 않도록 필요한 값만 담는다.
spec_service 에서 SpecItem → SpecRule 로 바꿔 넘긴다 (SpecRule.from_model).
"""
from dataclasses import dataclass

from app.core.enums import SpecType


@dataclass(frozen=True)
class SpecRule:
    item_name: str
    unit: str | None = None
    lsl: float | None = None
    usl: float | None = None
    spec_type: SpecType = SpecType.QUANTITATIVE
    is_required: bool = True  # False 면 CoA 에 없어도 누락 항목을 만들지 않는다 (v1.4안, DEMO-R 의 별도 성적서 항목)

    @property
    def is_quantitative(self) -> bool:
        return self.spec_type == SpecType.QUANTITATIVE

    @classmethod
    def from_model(cls, spec) -> "SpecRule":
        """app.models.SpecItem (또는 같은 속성을 가진 객체) 에서 생성."""
        return cls(spec.item_name, spec.unit, spec.lsl, spec.usl, SpecType(spec.spec_type),
                   bool(getattr(spec, "is_required", True)))


def name_key(name: str | None) -> str:
    """항목명 비교용 키. 대소문자·앞뒤 공백 무시."""
    return (name or "").strip().casefold()
