"""[담당: 홍채령] 로그인 잠금 테스트 (운영 정책 3단계: 5번 연속 실패 → 15분 잠금). 실제 DB 필요.

시간은 login_guard._now 를 바꿔 끼워 조절한다. 다른 IP 는 TRUST_PROXY_HEADERS + X-Forwarded-For 로 흉내 낸다.
"""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.enums import Role
from app.core.safe_log import username_tag
from app.core.security import create_access_token, hash_password
from app.models import LoginFailure, User
from app.services import login_guard

PW = "abcd1234"
BAD = "wrong9999"


@pytest.fixture
def clock(monkeypatch):
    """clock.now 를 옮기면 서버가 보는 현재 시각이 바뀐다."""
    class Clock:
        now = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)

        def advance(self, **kw):
            self.now += timedelta(**kw)
    c = Clock()
    monkeypatch.setattr(login_guard, "_now", lambda: c.now)
    return c


@pytest.fixture
def kim(db) -> User:
    u = User(username="kim", name="김검수", role=Role.USER, password_hash=hash_password(PW))
    db.add(u)
    db.commit()
    return u


def login(client, username="kim", password=PW, ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/api/v1/auth/login", json={"username": username, "password": password}, headers=headers)


def code(r):
    return r.status_code, r.json()["error"]["code"] if r.status_code >= 400 else None


def fail(client, n, **kw):
    return [login(client, password=BAD, **kw) for _ in range(n)]


def test_fifth_failure_locks(client, kim, clock):
    for r in fail(client, 4):
        assert code(r) == (401, "INVALID_CREDENTIALS")
    r = login(client, password=BAD)
    assert code(r) == (429, "ACCOUNT_LOCKED")
    assert r.json()["error"]["message"] == "로그인 시도가 너무 많아 잠겼습니다. 15분 후 다시 시도하세요"
    assert r.headers["retry-after"] == str(15 * 60)


def test_locked_rejects_correct_password(client, kim, clock):
    fail(client, 5)
    clock.advance(minutes=10, seconds=30)
    r = login(client)  # 비밀번호가 맞아도 막힌다
    assert code(r) == (429, "ACCOUNT_LOCKED")
    assert "5분 후" in r.json()["error"]["message"]  # 4분 30초 남음 → 올림 5분
    assert r.headers["retry-after"] == str(4 * 60 + 30)


def test_lock_expires_and_counting_restarts(client, kim, clock, db):
    fail(client, 5)
    clock.advance(minutes=15, seconds=1)
    assert code(login(client, password=BAD)) == (401, "INVALID_CREDENTIALS")  # 처음부터 1회
    row = db.scalar(select(LoginFailure))
    assert row.fail_count == 1 and row.locked_until is None
    assert login(client).status_code == 200


def test_success_resets_count(client, kim, clock, db):
    fail(client, 4)
    assert login(client).status_code == 200
    assert db.scalar(select(func.count()).select_from(LoginFailure)) == 0
    for r in fail(client, 4):  # 다시 4번 틀려도 안 잠긴다
        assert code(r) == (401, "INVALID_CREDENTIALS")


def test_old_failures_forgotten(client, kim, clock):
    """마지막 실패 뒤 15분이 지나면 연속 실패로 보지 않는다."""
    fail(client, 4)
    clock.advance(minutes=16)
    for r in fail(client, 4):
        assert code(r) == (401, "INVALID_CREDENTIALS")


def test_other_ip_not_locked(client, kim, clock, monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    fail(client, 5, ip="10.0.0.66")
    assert code(login(client, ip="10.0.0.66")) == (429, "ACCOUNT_LOCKED")
    assert login(client, ip="10.0.0.7").status_code == 200  # 진짜 사용자 PC 는 그대로


def test_forwarded_header_ignored_by_default(client, kim, clock):
    """TRUST_PROXY_HEADERS=false 면 헤더를 바꿔도 같은 IP 로 본다 (잠금 우회 불가)."""
    for i in range(5):
        r = login(client, password=BAD, ip=f"1.1.1.{i}")
    assert code(r) == (429, "ACCOUNT_LOCKED")
    assert code(login(client, ip="9.9.9.9")) == (429, "ACCOUNT_LOCKED")


def test_forwarded_uses_last_entry(client, kim, clock, monkeypatch):
    """프록시가 덧붙인 마지막 IP 를 쓴다. 맨 앞(사용자가 꾸민 값)을 바꿔도 같은 IP 로 센다."""
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    for i in range(5):
        r = login(client, password=BAD, ip=f"6.6.6.{i}, 10.0.0.5")
    assert code(r) == (429, "ACCOUNT_LOCKED")


def test_unknown_username_counted_same_error(client, db, clock):
    for r in fail(client, 4, username="ghost"):
        assert code(r) == (401, "INVALID_CREDENTIALS")
    assert code(login(client, username="ghost", password=BAD)) == (429, "ACCOUNT_LOCKED")


def test_username_case_insensitive(client, kim, clock):
    fail(client, 3)
    fail(client, 2, username="KIM")
    assert code(login(client)) == (429, "ACCOUNT_LOCKED")


def test_password_change_wrong_current_counts(client, kim, clock):
    h = {"Authorization": f"Bearer {create_access_token(kim.id)}"}
    body = {"current_password": BAD, "new_password": "newpass99"}
    fail(client, 2)
    for _ in range(2):
        assert code(client.post("/api/v1/auth/password", json=body, headers=h)) == (400, "WRONG_PASSWORD")
    assert code(client.post("/api/v1/auth/password", json=body, headers=h)) == (429, "ACCOUNT_LOCKED")
    ok = {"current_password": PW, "new_password": "newpass99"}
    assert code(client.post("/api/v1/auth/password", json=ok, headers=h)) == (429, "ACCOUNT_LOCKED")
    assert code(login(client)) == (429, "ACCOUNT_LOCKED")


def test_password_change_success_clears(client, kim, clock, db):
    h = {"Authorization": f"Bearer {create_access_token(kim.id)}"}
    fail(client, 4)
    r = client.post("/api/v1/auth/password", json={"current_password": PW, "new_password": "newpass99"}, headers=h)
    assert r.status_code == 200
    assert db.scalar(select(func.count()).select_from(LoginFailure)) == 0


def test_admin_reset_clears_lock_all_ips(client, kim, db, clock, monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    boss = User(username="boss", name="관리자", role=Role.ADMIN, password_hash=hash_password(PW))
    db.add(boss)
    db.commit()
    fail(client, 5, ip="10.0.0.1")
    fail(client, 5, ip="10.0.0.2")
    r = client.post(f"/api/v1/users/{kim.id}/reset-password", json={"new_password": "temp5678"},
                    headers={"Authorization": f"Bearer {create_access_token(boss.id)}"})
    assert r.status_code == 200
    assert db.scalar(select(func.count()).select_from(LoginFailure)) == 0
    assert login(client, password="temp5678", ip="10.0.0.1").status_code == 200


def test_logs_have_no_password(client, kim, clock, caplog):
    """운영 정책 3장: 로그에 비밀번호도, 아이디 원문도 남기지 않는다. 사용자 id 와 아이디 표식만."""
    caplog.set_level(logging.WARNING, logger="app.services.login_guard")
    fail(client, 5)
    tag = username_tag("kim")
    assert f"로그인 실패: user_id={kim.id} user={tag} ip=testclient count=1" in caplog.text
    assert f"로그인 잠김: user_id={kim.id} user={tag} ip=testclient" in caplog.text
    assert BAD not in caplog.text and PW not in caplog.text
    assert "kim" not in caplog.text and "김검수" not in caplog.text


def test_logs_for_unknown_username_have_no_raw_name(client, kim, clock, caplog):
    """없는 아이디 칸에 비밀번호를 잘못 넣은 경우에도 그 글자가 로그에 남지 않는다."""
    caplog.set_level(logging.WARNING, logger="app.services.login_guard")
    login(client, username="MySecretPw99", password=BAD)
    assert "mysecretpw99" not in caplog.text.lower()
    assert f"user_id=- user={username_tag('MySecretPw99')}" in caplog.text


def test_lock_survives_new_session(client, kim, clock, db):
    """DB 에 저장되므로 (서버 재시작처럼) 새 세션에서도 잠겨 있다."""
    fail(client, 5)
    db.expire_all()
    row = db.scalar(select(LoginFailure))
    assert row.locked_until == clock.now + timedelta(minutes=15)
