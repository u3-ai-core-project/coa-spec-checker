"""[담당: 장수민] 시드 적재 테스트 — 저장소의 실제 CSV(seeds/data)를 테스트 DB 에 넣어 본다. 실제 DB 필요."""
from sqlalchemy import func, select

from app.models import ItemMapping, SpecItem, SpecSet
from app.services import spec_service
from seeds.seed_mappings import seed_mappings
from seeds.seed_specs import seed_specs


def test_seed_specs_and_mappings_load_and_are_idempotent(db):
    sets, items = seed_specs(db)
    mappings = seed_mappings(db)
    assert sets >= 1 and items >= 1 and mappings >= 1

    # 다시 실행해도 추가되지 않는다 (관리자 수정값·manual 매핑 보호)
    assert seed_specs(db) == (0, 0) and seed_mappings(db) == 0
    assert db.scalar(select(func.count()).select_from(SpecItem)) == items


def test_seeded_material_has_default_set_and_judging_rules(db):
    seed_specs(db)
    for material_code in db.scalars(select(SpecSet.material_code).distinct()):
        default = spec_service.get_default_set(db, material_code)
        assert default is not None and default.is_default
        rules = spec_service.get_rules(db, default.id)
        assert rules and all(r.item_name for r in rules)


def test_seed_does_not_overwrite_manual_mapping(db):
    db.add(ItemMapping(material_code="LI2CO3", raw_name="Assay", normalized_name="수동지정", source="manual"))
    db.commit()
    seed_mappings(db)
    row = db.scalar(select(ItemMapping).where(ItemMapping.raw_name == "Assay"))
    assert (row.normalized_name, row.source) == ("수동지정", "manual")
