"""[담당: 장수민] item_mappings 초기값 적재 (명세 2.5, v1.4안: 원자재별 사전).

입력: seeds/data/item_mappings.csv
    material_code, raw_name, normalized_name

동작
  - (material_code, raw_name) 이 이미 있으면 건너뛴다. 담당자가 검수 중 고친 manual 항목을 덮어쓰지 않기 위해서다.
  - source 는 seed 로 넣는다.

※ 현재 CSV 는 기획안·조사 문서에 나온 표기만 넣은 임시값이다 (소성훈 님 매핑 사전 초기값으로 교체 예정).
   "Heavy metals (as Pb)" 는 Pb 가 아니라 중금속 총량이다. 중금속 총량 → Pb 판정은 교차 규칙
   (app/services/judgement/cross_rules.py) 이 처리한다.

실행: python -m seeds.seed_mappings   (전체 시드는 python -m seeds.seed)
"""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ItemMappingSource
from app.db.session import SessionLocal
from app.models import ItemMapping

DATA_DIR = Path(__file__).parent / "data"


def seed_mappings(db: Session, path: Path = DATA_DIR / "item_mappings.csv") -> int:
    """추가한 매핑 수. commit 까지 한다."""
    if not path.exists():
        return 0
    existing = {tuple(r) for r in db.execute(select(ItemMapping.material_code, ItemMapping.raw_name))}
    added = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            material_code = (row.get("material_code") or "").strip()
            raw_name = (row.get("raw_name") or "").strip()
            normalized = (row.get("normalized_name") or "").strip()
            if not (material_code and raw_name and normalized):
                continue
            if (material_code, raw_name) in existing:
                continue
            db.add(ItemMapping(material_code=material_code, raw_name=raw_name,
                               normalized_name=normalized, source=ItemMappingSource.SEED))
            existing.add((material_code, raw_name))
            added += 1
    db.commit()
    return added


if __name__ == "__main__":
    with SessionLocal() as session:
        print(f"item_mappings: {seed_mappings(session)}건 추가")
