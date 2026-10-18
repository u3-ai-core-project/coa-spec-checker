"""[담당: 장수민] item_mappings 조회, manual 누적 (명세 2.5, 4.9).

- 담당자가 검수 중 항목명을 고치면 (material_code, raw_name) → normalized_name 을 source=manual 로 남긴다.
  같은 raw_name 이 이미 있으면 덮어쓴다 (seed 든 manual 이든). 다음 입고부터 같은 표기는 사전으로 바로 매핑된다.
- 사전 조회(lookup)는 AI 추출 파트가 정규화할 때 쓰는 입구다. 고도영 님 어댑터가 이 함수 또는 같은 쿼리를 쓰면 된다.
commit 은 호출한 쪽에서 한다.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ItemMappingSource
from app.models import ItemMapping


def lookup(db: Session, material_code: str, raw_name: str) -> str | None:
    """협력사 항목명 → 사내 표준 항목명. 사전에 없으면 None (그때 AI 가 추정)."""
    return db.scalar(
        select(ItemMapping.normalized_name)
        .where(ItemMapping.material_code == material_code, ItemMapping.raw_name == raw_name.strip())
    )


def upsert_manual(db: Session, *, material_code: str, raw_name: str, normalized_name: str, user_id: int) -> ItemMapping:
    """담당자 수정 내용을 사전에 누적한다 (명세 4.9: 이미 같은 raw_name 이 있으면 덮어쓴다)."""
    raw_name = raw_name.strip()
    row = db.scalar(
        select(ItemMapping).where(ItemMapping.material_code == material_code, ItemMapping.raw_name == raw_name)
    )
    if row is None:
        row = ItemMapping(material_code=material_code, raw_name=raw_name)
        db.add(row)
    row.normalized_name = normalized_name
    row.source = ItemMappingSource.MANUAL
    row.created_by = user_id
    return row
