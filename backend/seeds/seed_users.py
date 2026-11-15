"""[담당: 홍채령] 관리자 1, 사용자 1 이상

개발·시연용 계정이다. 이미 있는 username 은 건너뛴다.
실행: python -m seeds.seed_users
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User

# (username, password, name, role)
SEED_USERS = [
    ("admin", "admin1234", "관리자", Role.ADMIN),
    ("user1", "user1234", "검수담당1", Role.USER),
    ("user2", "user1234", "검수담당2", Role.USER),
]


def seed_users(db: Session) -> int:
    """추가한 계정 수를 반환한다."""
    existing = set(db.scalars(select(User.username)))
    added = 0
    for username, password, name, role in SEED_USERS:
        if username in existing:
            continue
        db.add(User(username=username, password_hash=hash_password(password), name=name, role=role))
        added += 1
    db.commit()
    return added


if __name__ == "__main__":
    with SessionLocal() as session:
        print(f"users: {seed_users(session)}건 추가")
