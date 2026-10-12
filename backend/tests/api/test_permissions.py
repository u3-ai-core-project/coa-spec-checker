"""[담당: 홍채령] USER로 관리자 기능 접근 시 403, 토큰 없음·만료·위조 401"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def assert_unauthorized(r):
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert r.headers["www-authenticate"] == "Bearer"


def test_no_token(client, db):
    assert_unauthorized(client.get("/api/v1/auth/me"))


def test_expired_token(client, user):
    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


def test_forged_token(client, user):
    token = jwt.encode({"sub": str(user.id)}, "not-the-server-secret", algorithm=settings.JWT_ALGORITHM)
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


@pytest.mark.parametrize("token", ["garbage", "a.b.c"])
def test_malformed_token(client, db, token):
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


def test_token_of_deleted_user(client, user, db):
    token = create_access_token(user.id)
    db.delete(user)
    db.commit()
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


def test_user_cannot_list_users(client, user):
    r = client.get("/api/v1/users", headers=bearer(create_access_token(user.id)))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_admin_lists_users(client, user, admin):
    r = client.get("/api/v1/users", headers=bearer(create_access_token(admin.id)))
    assert r.status_code == 200
    assert r.json()["data"] == [
        {"id": user.id, "name": "김사용", "role": "USER"},
        {"id": admin.id, "name": "관리자", "role": "ADMIN"},
    ]


def test_user_token_works_on_other_api(client, user, db):
    """장수민 쪽 API 도 실제 토큰으로 통과하는지 (의존성 오버라이드 없이)."""
    r = client.get("/api/v1/documents", headers=bearer(create_access_token(user.id)))
    assert r.status_code == 200
