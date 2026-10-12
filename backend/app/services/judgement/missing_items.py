"""[담당: 장수민] 사내 규격에 있고 CoA 에 없는 누락 항목 생성 (명세 2.1, 2.3).

누락 항목은 mapping_source=spec 이고 raw_name, raw_value, confidence, bbox 가 null 이다.
item_id 는 spec-001, spec-002 ... 순서로 붙인다.
"""
from collections.abc import Iterable

from app.core.enums import MappingSource
from app.schemas.extraction import ExtractedItem
from app.services.judgement.spec_rule import SpecRule, name_key


def build_missing_items(items: Iterable[ExtractedItem], specs: Iterable[SpecRule]) -> list[ExtractedItem]:
    present = {name_key(i.normalized_name) for i in items}
    missing = [s for s in specs if name_key(s.item_name) not in present]
    return [
        ExtractedItem(
            item_id=f"spec-{n:03d}",
            normalized_name=s.item_name,
            mapping_source=MappingSource.SPEC,
            unit=s.unit,
        )
        for n, s in enumerate(missing, start=1)
    ]
