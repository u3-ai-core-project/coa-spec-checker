"""[담당: 공통(장수민 생성, 둘 다 수정)] 시드 적재 실행 스크립트.

순서: 사용자 → 규격 세트·항목 → 항목명 매핑 사전. 이미 있는 데이터는 건너뛰므로 여러 번 실행해도 된다.
실행: python -m seeds.seed   (alembic upgrade head 다음에 실행)
"""
from app.db.session import SessionLocal
from seeds.seed_mappings import seed_mappings
from seeds.seed_specs import seed_specs
from seeds.seed_users import seed_users


def main() -> None:
    with SessionLocal() as db:
        print(f"users: {seed_users(db)}건 추가")
        sets, items = seed_specs(db)
        print(f"spec_sets: {sets}건, spec_items: {items}건 추가")
        print(f"item_mappings: {seed_mappings(db)}건 추가")


if __name__ == "__main__":
    main()
