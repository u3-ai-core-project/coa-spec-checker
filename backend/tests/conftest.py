"""[담당: 공통] 테스트 공통 픽스처.

DB 가 필요한 테스트는 db, user, admin, auth_client 픽스처를 쓴다.
테스트 DB 는 TEST_DATABASE_URL (기본: 같은 서버의 coa_test) 이며, 없으면 자동으로 만든다.
DB 서버에 연결할 수 없으면 DB 테스트는 건너뛴다 (skip).
"""
import os

# app 을 import 하기 전에 DB 주소를 테스트 DB 로 바꾼다 (.env 보다 환경변수가 우선)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://coa:coa@localhost:5432/coa_test")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.enums import Role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}):
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def _schema():
    try:
        _ensure_database()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    except OperationalError as e:
        pytest.skip(f"테스트 DB 에 연결할 수 없음: {e.orig}")
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(_schema, tmp_path, monkeypatch):
    """테스트마다 빈 테이블 + 임시 업로드 폴더."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = SessionLocal()
    yield session
    session.close()


def _make_user(db, username: str, name: str, role: Role) -> User:
    u = User(username=username, password_hash="x", name=name, role=role)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def user(db) -> User:
    return _make_user(db, "user1", "김사용", Role.USER)


@pytest.fixture
def admin(db) -> User:
    return _make_user(db, "admin", "관리자", Role.ADMIN)


@pytest.fixture
def auth_client(client, user):
    """user 로 로그인한 것처럼 동작하는 클라이언트. 다른 사용자는 login_as(admin) 처럼 바꾼다."""
    def login_as(u: User):
        app.dependency_overrides[get_current_user] = lambda: u

    login_as(user)
    client.login_as = login_as
    yield client
    app.dependency_overrides.pop(get_current_user, None)
