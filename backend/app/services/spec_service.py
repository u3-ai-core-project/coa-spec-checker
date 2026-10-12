"""[담당: 장수민] material_code 별 사내 규격 조회·수정."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SpecItem
from app.services.judgement.spec_rule import SpecRule


def material_exists(db: Session, material_code: str) -> bool:
    return db.scalar(select(SpecItem.id).where(SpecItem.material_code == material_code).limit(1)) is not None


def get_specs(db: Session, material_code: str) -> list[SpecItem]:
    return list(db.scalars(select(SpecItem).where(SpecItem.material_code == material_code).order_by(SpecItem.id)))


def get_rules(db: Session, material_code: str) -> list[SpecRule]:
    """판정 모듈에 넘길 규격 목록."""
    return [SpecRule.from_model(s) for s in get_specs(db, material_code)]


def get_material_info(db: Session, material_code: str) -> tuple[str | None, str | None]:
    """(원자재명, 사내 규격 등급). 규격이 없으면 (None, None)."""
    row = db.execute(
        select(SpecItem.material_name, SpecItem.grade)
        .where(SpecItem.material_code == material_code)
        .order_by(SpecItem.grade.is_(None), SpecItem.id)
        .limit(1)
    ).first()
    return (row.material_name, row.grade) if row else (None, None)
