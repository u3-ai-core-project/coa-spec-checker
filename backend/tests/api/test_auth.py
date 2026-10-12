"""[담당: 홍채령]"""
import pytest

from app.core.enums import Role
from app.core.security import hash_password, verify_password
from app.models import User
from seeds.seed_users import SEED_USERS, seed_users


@pytest.fixture
def member(db) -> User:
    u = User(username="kim", password_hash=hash_password("pw1234"), name="김검수", role=Role.USER)
    db.add(u)
    db.commit()
    return u


def login(client, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_hash_and_verify():
    h = hash_password("secret")
    assert h != "secret"
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)
    assert not verify_password("secret", "x")  # 해시 형식이 아니면 불일치


def test_login_success(client, member):
    r = login(client, "kim", "pw1234")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600
    assert data["access_token"]
    assert data["user"] == {"id": member.id, "name": "김검수", "role": "USER"}


@pytest.mark.parametrize("username, password", [("kim", "wrong"), ("nobody", "pw1234")])
def test_login_invalid_credentials(client, member, username, password):
    r = login(client, username, password)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_missing_field(client, db):
    r = client.post("/api/v1/auth/login", json={"username": "kim"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_me_with_login_token(client, member):
    token = login(client, "kim", "pw1234").json()["data"]["access_token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {
        "success": True,
        "data": {"id": member.id, "username": "kim", "name": "김검수", "role": "USER"},
        "error": None,
    }


def test_seed_users_is_idempotent(client, db):
    assert seed_users(db) == len(SEED_USERS)
    assert seed_users(db) == 0
    roles = {role for *_, role in SEED_USERS}
    assert roles == {Role.ADMIN, Role.USER}
    username, password, *_ = SEED_USERS[0]
    assert login(client, username, password).status_code == 200
