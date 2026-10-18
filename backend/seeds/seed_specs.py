"""[담당: 장수민] 사내 규격 세트·항목 초기값 적재 (명세 v1.4안 2.5).

입력 파일 (seeds/data/)
  spec_sets.csv          세트 1행 = 원자재 + 등급 + 버전
      code, material_code, material_name, grade, version, source, is_default, description
  spec_items_*.csv       항목 1행. 원자재별로 파일을 나눠도 된다 (spec_items_li2co3.csv, spec_items_lioh.csv ...)
      spec_set_code, item_name, unit, lsl, usl, spec_type(정량/정성), is_required(true/false), source

동작
  - 이미 있는 세트(code)·항목(세트 + item_name)은 건너뛴다. 관리자가 화면에서 고친 값을 덮어쓰지 않기 위해서다.
    값을 바꾸려면 DB 에서 지우고 다시 적재하거나, 규격 수정 API(4.21)를 쓴다.
  - 빈 칸은 None 으로 넣는다 (lsl 만 있으면 하한만 있는 항목).

※ 현재 CSV 의 탄산리튬 D1 값은 기획안·요청 문서에 적힌 임시값이다. 소성훈 님 규격 CSV 를 받으면 파일만 바꾸면 된다.
   item_name 은 AI 추출 결과의 normalized_name 과 같아야 판정된다 (고도영 님과 확정 필요).

실행: python -m seeds.seed_specs   (전체 시드는 python -m seeds.seed)
"""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SpecType
from app.db.session import SessionLocal
from app.models import SpecItem, SpecSet

DATA_DIR = Path(__file__).parent / "data"


def _blank_to_none(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _float(v: str | None) -> float | None:
    v = _blank_to_none(v)
    return float(v) if v is not None else None


def _bool(v: str | None, default: bool) -> bool:
    v = _blank_to_none(v)
    if v is None:
        return default
    return v.lower() in ("true", "1", "y", "yes", "o")


def _read(path: Path) -> list[dict]:
    # utf-8-sig: 엑셀에서 저장한 CSV 의 BOM 을 허용
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if any((v or "").strip() for v in row.values())]


def seed_spec_sets(db: Session, path: Path = DATA_DIR / "spec_sets.csv") -> int:
    if not path.exists():
        return 0
    existing = set(db.scalars(select(SpecSet.code)))
    added = 0
    for row in _read(path):
        code = row["code"].strip()
        if code in existing:
            continue
        db.add(SpecSet(
            code=code,
            material_code=row["material_code"].strip(),
            material_name=row["material_name"].strip(),
            grade=_blank_to_none(row.get("grade")),
            version=_blank_to_none(row.get("version")),
            source=_blank_to_none(row.get("source")),
            description=_blank_to_none(row.get("description")),
            is_default=_bool(row.get("is_default"), False),
        ))
        existing.add(code)
        added += 1
    db.flush()
    return added


def seed_spec_items(db: Session, data_dir: Path = DATA_DIR) -> int:
    sets = {s.code: s for s in db.scalars(select(SpecSet))}
    existing = {(i.spec_set_id, i.item_name) for i in db.scalars(select(SpecItem))}
    added = 0
    for path in sorted(data_dir.glob("spec_items_*.csv")):
        for line_no, row in enumerate(_read(path), start=2):
            set_code = row["spec_set_code"].strip()
            spec_set = sets.get(set_code)
            if spec_set is None:
                raise ValueError(f"{path.name}:{line_no} spec_sets.csv 에 없는 세트 코드: {set_code}")
            key = (spec_set.id, row["item_name"].strip())
            if key in existing:
                continue
            db.add(SpecItem(
                spec_set_id=spec_set.id,
                item_name=key[1],
                unit=_blank_to_none(row.get("unit")),
                lsl=_float(row.get("lsl")),
                usl=_float(row.get("usl")),
                spec_type=SpecType(row["spec_type"].strip()),
                is_required=_bool(row.get("is_required"), True),
                source=_blank_to_none(row.get("source")),
            ))
            existing.add(key)
            added += 1
    db.flush()
    return added


def seed_specs(db: Session, data_dir: Path = DATA_DIR) -> tuple[int, int]:
    """(추가한 세트 수, 추가한 항목 수). commit 까지 한다."""
    sets = seed_spec_sets(db, data_dir / "spec_sets.csv")
    items = seed_spec_items(db, data_dir)
    db.commit()
    return sets, items


if __name__ == "__main__":
    with SessionLocal() as session:
        s, i = seed_specs(session)
        print(f"spec_sets: {s}건, spec_items: {i}건 추가")
