"""[담당: 홍채령] 계정 관리 테스트 (운영 정책 2단계). 실제 DB 필요.

비밀번호 규칙, 비활성 계정, 첫 로그인 비밀번호 변경, 관리자 계정 API, 본인·마지막 관리자 보호, 감사 로그.
여기서는 dependency_overrides 대신 실제 토큰을 쓴다 (비활성·비밀번호 변경 검사가 토큰 검증 단계에 있으므로).
"""
import logging

import pytest

from app.core.enums import Role
from app.core.errors import AppException
from app.core.security import create_access_token, hash_password, validate_password, verify_password
from app.models import User

GOOD = "abcd1234"
NEW = "newpass99"


def bearer(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id)}"}


def make(db, username, role=Role.USER, password=GOOD, **kw) -> User:
    u = User(username=username, name=username, role=role, password_hash=hash_password(password), **kw)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def boss(db) -> User:
    return make(db, "boss", Role.ADMIN)


@pytest.fixture
def worker(db) -> User:
    return make(db, "worker")


def err(r):
    return r.status_code, r.json()["error"]["code"]


def login(client, username, password=GOOD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


# ---- 비밀번호 규칙 -----------------------------------------------------------
@pytest.mark.parametrize("pw, part", [
    ("abc123", "8자 이상"),
    ("abcdefgh", "숫자"),
    ("12345678", "영문자"),
    ("가나다라마바사1", "영문자"),
    ("a1" + "가" * 24, "너무 깁니다"),  # 2 + 72 바이트
])
def test_password_rule_rejects(pw, part):
    with pytest.raises(AppException) as e:
        validate_password(pw)
    assert e.value.code.name == "INVALID_PASSWORD"
    assert part in e.value.message


@pytest.mark.parametrize("pw", ["abcd1234", "A1b2c3d4!", "a1" + "x" * 70])
def test_password_rule_accepts(pw):
    validate_password(pw)


# ---- 로그인 -----------------------------------------------------------------
def test_inactive_user_cannot_login(client, db):
    make(db, "gone", is_active=False)
    assert err(login(client, "gone")) == (403, "ACCOUNT_DISABLED")
    # 비밀번호가 틀리면 비활성 여부를 알려 주지 않는다
    assert err(login(client, "gone", "wrong999")) == (401, "INVALID_CREDENTIALS")


def test_login_returns_must_change_password(client, db):
    make(db, "fresh", must_change_password=True)
    r = login(client, "fresh")
    assert r.status_code == 200
    assert r.json()["data"]["must_change_password"] is True


def test_deactivated_user_token_stops_working(client, db, boss, worker):
    headers = bearer(worker)
    assert client.get("/api/v1/documents", headers=headers).status_code == 200

    r = client.patch(f"/api/v1/users/{worker.id}/active", json={"is_active": False}, headers=bearer(boss))
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False

    for path in ("/api/v1/documents", "/api/v1/auth/me"):
        r = client.get(path, headers=headers)
        assert err(r) == (401, "UNAUTHORIZED")
        assert r.json()["error"]["message"] == "비활성화된 계정입니다. 관리자에게 문의하세요"


# ---- 비밀번호 변경 필요 상태 -------------------------------------------------
def test_must_change_password_blocks_other_apis(client, db):
    fresh = make(db, "fresh", must_change_password=True)
    h = bearer(fresh)
    for method, path in [("get", "/api/v1/documents"), ("get", "/api/v1/dashboard/summary"), ("get", "/api/v1/specs")]:
        r = getattr(client, method)(path, headers=h)
        assert err(r) == (403, "PASSWORD_CHANGE_REQUIRED")
    # me 는 된다
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200 and r.json()["data"]["must_change_password"] is True


def test_must_change_password_admin_blocked_too(client, db):
    fresh_admin = make(db, "newadmin", Role.ADMIN, must_change_password=True)
    assert err(client.get("/api/v1/users", headers=bearer(fresh_admin))) == (403, "PASSWORD_CHANGE_REQUIRED")


def test_change_password_clears_flag(client, db):
    fresh = make(db, "fresh", must_change_password=True)
    h = bearer(fresh)
    r = client.post("/api/v1/auth/password", json={"current_password": GOOD, "new_password": NEW}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["must_change_password"] is False
    assert client.get("/api/v1/documents", headers=h).status_code == 200  # 같은 토큰으로 바로 쓸 수 있다
    assert login(client, "fresh", NEW).status_code == 200
    assert err(login(client, "fresh", GOOD)) == (401, "INVALID_CREDENTIALS")


def test_change_password_wrong_current(client, worker, db):
    r = client.post("/api/v1/auth/password", json={"current_password": "nope1234", "new_password": NEW},
                    headers=bearer(worker))
    assert err(r) == (400, "WRONG_PASSWORD")
    db.refresh(worker)
    assert verify_password(GOOD, worker.password_hash)


def test_change_password_rule_and_same(client, worker):
    h = bearer(worker)
    r = client.post("/api/v1/auth/password", json={"current_password": GOOD, "new_password": "short1"}, headers=h)
    assert err(r) == (400, "INVALID_PASSWORD")
    r = client.post("/api/v1/auth/password", json={"current_password": GOOD, "new_password": GOOD}, headers=h)
    assert err(r) == (400, "INVALID_PASSWORD")
    assert r.json()["error"]["message"] == "새 비밀번호는 현재 비밀번호와 달라야 합니다"


def test_change_password_requires_token(client, db):
    r = client.post("/api/v1/auth/password", json={"current_password": GOOD, "new_password": NEW})
    assert err(r) == (401, "UNAUTHORIZED")


# ---- 관리자 계정 API ---------------------------------------------------------
def test_admin_creates_user(client, db, boss):
    r = client.post("/api/v1/users", headers=bearer(boss),
                    json={"username": "newbie", "name": " 신입 ", "role": "USER", "password": GOOD})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["username"] == "newbie" and data["name"] == "신입" and data["role"] == "USER"
    assert data["is_active"] is True and data["must_change_password"] is True
    assert "password" not in data and "password_hash" not in data and GOOD not in str(data)

    # 첫 로그인 → 비밀번호 변경 전에는 다른 API 를 못 쓴다
    r = login(client, "newbie")
    assert r.json()["data"]["must_change_password"] is True
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    assert err(client.get("/api/v1/documents", headers=h)) == (403, "PASSWORD_CHANGE_REQUIRED")
    client.post("/api/v1/auth/password", json={"current_password": GOOD, "new_password": NEW}, headers=h)
    assert client.get("/api/v1/documents", headers=h).status_code == 200


@pytest.mark.parametrize("username", ["worker", "WORKER"])
def test_create_user_duplicate(client, boss, worker, username):
    r = client.post("/api/v1/users", headers=bearer(boss),
                    json={"username": username, "name": "x", "password": GOOD})
    assert err(r) == (409, "USERNAME_TAKEN")


@pytest.mark.parametrize("body, code", [
    ({"username": "ok_name", "name": "x", "password": "weak"}, "INVALID_PASSWORD"),
    ({"username": "한글아이디", "name": "x", "password": GOOD}, "VALIDATION_ERROR"),
    ({"username": "ab", "name": "x", "password": GOOD}, "VALIDATION_ERROR"),
    ({"username": "ok_name", "name": "   ", "password": GOOD}, "VALIDATION_ERROR"),
    ({"username": "ok_name", "name": "x", "role": "ROOT", "password": GOOD}, "VALIDATION_ERROR"),
])
def test_create_user_invalid(client, boss, body, code):
    assert err(client.post("/api/v1/users", headers=bearer(boss), json=body)) == (400, code)


@pytest.mark.parametrize("method, suffix, body", [
    ("post", "", {"username": "x_user", "name": "x", "password": GOOD}),
    ("patch", "/{id}/role", {"role": "ADMIN"}),
    ("patch", "/{id}/active", {"is_active": False}),
    ("post", "/{id}/reset-password", {"new_password": NEW}),
])
def test_account_apis_admin_only(client, worker, boss, method, suffix, body):
    path = "/api/v1/users" + suffix.format(id=boss.id)
    assert err(getattr(client, method)(path, json=body, headers=bearer(worker))) == (403, "FORBIDDEN")


def test_change_role(client, boss, worker):
    r = client.patch(f"/api/v1/users/{worker.id}/role", json={"role": "ADMIN"}, headers=bearer(boss))
    assert r.status_code == 200 and r.json()["data"]["role"] == "ADMIN"
    # 이제 다른 활성 ADMIN 이 있으니 boss 를 낮출 수 있다 (worker 가 낮춤)
    r = client.patch(f"/api/v1/users/{boss.id}/role", json={"role": "USER"}, headers=bearer(worker))
    assert r.status_code == 200 and r.json()["data"]["role"] == "USER"


def test_unknown_user(client, boss):
    assert err(client.patch("/api/v1/users/9999/role", json={"role": "USER"}, headers=bearer(boss))) == (
        404, "USER_NOT_FOUND")


def test_admin_cannot_demote_or_deactivate_self(client, db, boss):
    make(db, "boss2", Role.ADMIN)  # 다른 관리자가 있어도 본인은 안 된다
    h = bearer(boss)
    assert err(client.patch(f"/api/v1/users/{boss.id}/role", json={"role": "USER"}, headers=h)) == (
        409, "CANNOT_CHANGE_SELF")
    assert err(client.patch(f"/api/v1/users/{boss.id}/active", json={"is_active": False}, headers=h)) == (
        409, "CANNOT_CHANGE_SELF")


def test_last_active_admin_protected(client, db, boss):
    """다른 ADMIN 이 있어도 비활성이면 활성 관리자는 boss 하나다. 그 boss 를 다른 관리자가 낮추거나 끌 수 없어야 하지만,
    비활성 관리자는 API 를 못 쓰므로 여기서는 서비스 함수로 직접 확인한다."""
    from app.services import user_service
    sleeping = make(db, "sleeping", Role.ADMIN, is_active=False)
    with pytest.raises(AppException) as e:
        user_service.set_active(db, sleeping, boss.id, False)
    assert e.value.code.name == "LAST_ADMIN"
    with pytest.raises(AppException) as e:
        user_service.change_role(db, sleeping, boss.id, Role.USER)
    assert e.value.code.name == "LAST_ADMIN"


def test_deactivate_and_reactivate(client, boss, worker):
    h = bearer(boss)
    assert client.patch(f"/api/v1/users/{worker.id}/active", json={"is_active": False}, headers=h).status_code == 200
    assert err(login(client, "worker")) == (403, "ACCOUNT_DISABLED")
    r = client.patch(f"/api/v1/users/{worker.id}/active", json={"is_active": True}, headers=h)
    assert r.json()["data"]["is_active"] is True
    assert login(client, "worker").status_code == 200


def test_deactivate_other_admin_ok_when_another_active(client, db, boss):
    other = make(db, "other_admin", Role.ADMIN)
    r = client.patch(f"/api/v1/users/{other.id}/active", json={"is_active": False}, headers=bearer(boss))
    assert r.status_code == 200


def test_reset_password(client, db, boss, worker):
    r = client.post(f"/api/v1/users/{worker.id}/reset-password", json={"new_password": "temp5678"},
                    headers=bearer(boss))
    assert r.status_code == 200 and r.json()["data"]["must_change_password"] is True
    assert err(login(client, "worker")) == (401, "INVALID_CREDENTIALS")
    r = login(client, "worker", "temp5678")
    assert r.json()["data"]["must_change_password"] is True
    r = client.post(f"/api/v1/users/{worker.id}/reset-password", json={"new_password": "weak"},
                    headers=bearer(boss))
    assert err(r) == (400, "INVALID_PASSWORD")


def test_list_includes_inactive(client, db, boss):
    make(db, "gone", is_active=False)
    data = client.get("/api/v1/users", headers=bearer(boss)).json()["data"]
    assert {d["username"]: d["is_active"] for d in data} == {"boss": True, "gone": False}


# ---- 감사 로그 ---------------------------------------------------------------
def test_account_changes_logged_without_passwords(client, db, boss, worker, caplog):
    caplog.set_level(logging.INFO, logger="app.services.user_service")
    h = bearer(boss)
    client.post("/api/v1/users", headers=h, json={"username": "logme", "name": "x", "password": "secret123"})
    client.patch(f"/api/v1/users/{worker.id}/role", json={"role": "ADMIN"}, headers=h)
    client.patch(f"/api/v1/users/{worker.id}/active", json={"is_active": False}, headers=h)
    client.post(f"/api/v1/users/{worker.id}/reset-password", json={"new_password": "temp5678"}, headers=h)

    text = caplog.text
    for action in ("create_user", "change_role", "deactivate", "reset_password"):
        assert f"actor=boss(id={boss.id}) action={action}" in text
    assert "target=worker" in text
    for secret in ("secret123", "temp5678", "$2b$"):
        assert secret not in text
