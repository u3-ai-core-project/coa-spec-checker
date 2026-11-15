"""[담당: 장수민] item_mappings 조회, manual 누적, 매핑 사전 API (명세 2.5, 4.9, v1.4 4.23).

- 담당자가 검수 중 항목명을 고치면 (material_code, raw_name) → normalized_name 을 source=manual 로 남긴다.
  같은 raw_name 이 이미 있으면 덮어쓴다 (seed 든 manual 이든). 다음 입고부터 같은 표기는 사전으로 바로 매핑된다.
- 사전 조회(lookup)는 AI 추출 파트가 정규화할 때 쓰는 입구다. 고도영 님 어댑터가 이 함수 또는 같은 쿼리를 쓰면 된다.
- 매핑 사전 API (화면 5-2): 목록 조회, 삭제(ADMIN), 단위·산화물 환산표 조회.
  등록 API 는 두지 않는다. 매핑은 검수 화면의 항목명 수정으로만 쌓인다 (실제 문서를 보고 고친 매핑이 가장 정확).
  잘못 고친 매핑은 다음 문서부터 계속 적용되므로 삭제는 둔다. 이미 판정한 문서는 바뀌지 않는다.
commit 은 호출한 쪽에서 한다.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import ItemMappingSource
from app.core.errors import AppException, ErrorCode
from app.models import ItemMapping, User
from app.schemas.mapping import ConversionsOut, MappingOut, OxideConversionOut, UnitConversionOut
from app.services.judgement.value_parser import oxide_element, ppm_factors


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


# ---------------------------------------------------------------------------
# 매핑 사전 API (v1.4 4.23)
# ---------------------------------------------------------------------------
def list_mappings(db: Session, *, material_code: str | None = None,
                  normalized_name: str | None = None) -> list[MappingOut]:
    """GET /mappings. 원자재 → 표준 항목명 → 협력사 항목명 순."""
    stmt = (select(ItemMapping, User.name).outerjoin(User, User.id == ItemMapping.created_by)
            .order_by(ItemMapping.material_code, ItemMapping.normalized_name, ItemMapping.raw_name))
    if material_code:
        stmt = stmt.where(ItemMapping.material_code == material_code)
    if normalized_name:
        stmt = stmt.where(ItemMapping.normalized_name == normalized_name)
    return [
        MappingOut(id=m.id, material_code=m.material_code, raw_name=m.raw_name, normalized_name=m.normalized_name,
                   source=m.source, created_by=user_name, created_at=m.created_at)
        for m, user_name in db.execute(stmt)
    ]


def delete_mapping(db: Session, mapping_id: int) -> int:
    """DELETE /mappings/{id}. 없으면 404 NOT_FOUND. commit 까지 한다."""
    row = db.get(ItemMapping, mapping_id)
    if row is None:
        raise AppException(ErrorCode.NOT_FOUND, "존재하지 않는 매핑입니다")
    db.delete(row)
    db.commit()
    return mapping_id


def conversions() -> ConversionsOut:
    """GET /mappings/conversions. 판정에 쓰는 서버 설정값을 그대로 보여 준다."""
    return ConversionsOut(
        units=[UnitConversionOut(from_=unit, to="ppm", factor=factor) for unit, factor in ppm_factors().items()],
        oxides=[OxideConversionOut(oxide=formula, element=oxide_element(formula), factor=factor)
                for formula, factor in settings.OXIDE_TO_ELEMENT.items()],
    )
