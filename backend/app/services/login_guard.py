"""[담당: 홍채령] 로그인 잠금 (운영 정책 3단계).

- (아이디 소문자, 접속 IP) 마다 연속 실패 횟수를 센다. LOGIN_MAX_FAILURES 번째 실패에서 LOGIN_LOCK_MINUTES 분 잠근다
- 잠긴 동안에는 비밀번호가 맞아도 429 ACCOUNT_LOCKED. 비밀번호를 확인하기 전에 막는다
- 잠금이 풀리면 처음부터 다시 센다. 마지막 실패 뒤 LOGIN_LOCK_MINUTES 분이 지나도 처음부터 센다
- 로그인 성공·비밀번호 변경 성공이면 그 (아이디, IP) 기록을 지운다. 관리자가 비밀번호를 초기화하면 그 아이디의 기록을 모두 지운다
- 로그에는 시각(로그 자체), 사용자 id(있는 계정일 때), 아이디 표식(username_tag), IP 만 남긴다.
  아이디 원문과 비밀번호는 남기지 않는다 (운영 정책 3장)
"""
import logging
import math
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppException, ErrorCode
from app.core.safe_log import username_tag
from app.models import LoginFailure

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """현재 시각 (UTC). 테스트에서 바꿔 끼워 시간을 조절한다."""
    return datetime.now(timezone.utc)


def _key(username: str) -> str:
    return username.strip().lower()[:100]


def client_ip(request: Request) -> str:
    """접속 IP. TRUST_PROXY_HEADERS 가 켜져 있을 때만 X-Forwarded-For 를 본다.

    프록시(nginx 등)는 받은 X-Forwarded-For 뒤에 자기가 본 IP 를 덧붙이므로 맨 마지막 값을 쓴다.
    맨 앞 값은 사용자가 마음대로 꾸밀 수 있다.
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            last = forwarded.split(",")[-1].strip()
            if last:
                return last[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _locked_error(locked_until: datetime, now: datetime) -> AppException:
    seconds = max(1, math.ceil((locked_until - now).total_seconds()))
    minutes = math.ceil(seconds / 60)
    return AppException(
        ErrorCode.ACCOUNT_LOCKED,
        f"로그인 시도가 너무 많아 잠겼습니다. {minutes}분 후 다시 시도하세요",
        headers={"Retry-After": str(seconds)},
    )


def ensure_not_locked(db: Session, username: str, ip: str) -> None:
    """잠겨 있으면 429 ACCOUNT_LOCKED. 잠금 시간이 지났으면 기록을 지워 처음부터 다시 세게 한다."""
    row = db.scalar(select(LoginFailure).where(LoginFailure.username == _key(username), LoginFailure.ip == ip))
    if row is None or row.locked_until is None:
        return
    now = _now()
    if row.locked_until > now:
        raise _locked_error(row.locked_until, now)
    db.delete(row)
    db.commit()


def record_failure(db: Session, username: str, ip: str, user_id: int | None = None) -> None:
    """실패 1회 기록. LOGIN_MAX_FAILURES 번째면 잠그고 429 ACCOUNT_LOCKED 를 던진다. commit 까지 한다.

    user_id: 있는 계정이면 그 id (로그용). 없는 아이디면 None.

    동시에 여러 요청이 와도 횟수가 빠지지 않도록 INSERT ... ON CONFLICT 로 한 번에 더한다.
    """
    key, now = _key(username), _now()
    window_start = now - timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
    table = LoginFailure.__table__
    stmt = insert(table).values(username=key, ip=ip, fail_count=1, last_failed_at=now)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_login_failures_username_ip",
        set_={
            # 마지막 실패가 LOGIN_LOCK_MINUTES 분보다 오래전이면 처음부터(1) 센다
            "fail_count": case((table.c.last_failed_at < window_start, 1), else_=table.c.fail_count + 1),
            "last_failed_at": now,
        },
    ).returning(table.c.fail_count)
    count = db.execute(stmt).scalar_one()
    if count >= settings.LOGIN_MAX_FAILURES:
        locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
        db.execute(table.update().where(table.c.username == key, table.c.ip == ip).values(locked_until=locked_until))
        db.commit()
        logger.warning("로그인 잠김: user_id=%s user=%s ip=%s until=%s",
                       user_id if user_id is not None else "-", username_tag(key), ip, locked_until.isoformat())
        raise _locked_error(locked_until, now)
    db.commit()
    logger.warning("로그인 실패: user_id=%s user=%s ip=%s count=%d",
                   user_id if user_id is not None else "-", username_tag(key), ip, count)


def clear(db: Session, username: str, ip: str | None = None) -> None:
    """실패 기록을 지운다. ip 를 주면 그 IP 만, 안 주면 그 아이디의 모든 IP. commit 은 호출한 쪽에서 한다."""
    stmt = delete(LoginFailure).where(LoginFailure.username == _key(username))
    if ip is not None:
        stmt = stmt.where(LoginFailure.ip == ip)
    db.execute(stmt)
