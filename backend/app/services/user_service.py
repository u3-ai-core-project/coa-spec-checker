"""[담당: 홍채령] 로그인 인증, 사용자 조회, 계정 관리 (운영 정책 2단계).

계정 관리 정책:
- 공개 회원가입은 없다. ADMIN 이 초기 비밀번호로 계정을 만든다
- 만든 계정과 비밀번호를 초기화한 계정은 첫 로그인 때 비밀번호를 바꿔야 한다 (must_change_password)
- 계정은 지우지 않고 비활성화한다 (처분·검수 이력의 user_id 를 지키기 위해)
- 관리자는 본인을 비활성화하거나 USER 로 낮출 수 없고, 마지막 활성 ADMIN 도 그렇게 할 수 없다

계정 변경은 서버 로그에 남긴다 (누가, 누구를, 무엇을). 비밀번호와 해시는 절대 남기지 않는다.
"""
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.errors import AppException, ErrorCode
from app.core.security import hash_password, validate_password, verify_password
from app.models import User
from app.services import login_guard

logger = logging.getLogger(__name__)


def _audit(actor: User, action: str, target: User, detail: str = "") -> None:
    """계정 변경 기록. 비밀번호·해시는 넣지 않는다."""
    logger.info("계정 변경: actor=%s(id=%s) action=%s target=%s(id=%s)%s",
                actor.username, actor.id, action, target.username, target.id, f" {detail}" if detail else "")


# 없는 아이디일 때도 bcrypt 검사를 한 번 해서 응답 시간으로 아이디 존재 여부를 알 수 없게 한다
_DUMMY_HASH = hash_password("dummy-password-0")


def authenticate(db: Session, username: str, password: str, ip: str) -> User:
    """아이디·비밀번호가 맞으면 User, 아니면 401 INVALID_CREDENTIALS (어느 쪽이 틀렸는지 구분하지 않음).

    - (아이디, IP) 가 잠겨 있으면 비밀번호를 보기 전에 429 ACCOUNT_LOCKED (운영 정책 3단계)
    - 틀리면 실패 횟수 +1. LOGIN_MAX_FAILURES 번째 실패면 그 자리에서 429 ACCOUNT_LOCKED. 없는 아이디도 똑같이 센다
    - 성공하면 그 (아이디, IP) 의 실패 기록을 지운다
    - 비밀번호가 맞아도 비활성 계정이면 403 ACCOUNT_DISABLED. 비밀번호를 모르는 사람에게는 비활성 여부를 알려 주지 않는다
    """
    login_guard.ensure_not_locked(db, username, ip)
    user = db.scalar(select(User).where(User.username == username))
    password_ok = verify_password(password, user.password_hash if user is not None else _DUMMY_HASH)
    if user is None or not password_ok:
        login_guard.record_failure(db, username, ip)
        raise AppException(ErrorCode.INVALID_CREDENTIALS)
    if not user.is_active:
        raise AppException(ErrorCode.ACCOUNT_DISABLED)
    login_guard.clear(db, username, ip)
    db.commit()
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppException(ErrorCode.USER_NOT_FOUND)
    return user


# ---------------------------------------------------------------------------
# 본인 비밀번호 변경
# ---------------------------------------------------------------------------
def change_own_password(db: Session, user: User, current_password: str, new_password: str, ip: str) -> User:
    """POST /auth/password. 현재 비밀번호 확인 → 규칙 검사 → 이전과 달라야 함. must_change_password 를 끈다. commit 까지 한다.

    현재 비밀번호를 틀리는 것도 로그인 실패와 같이 센다 (토큰을 훔친 사람이 비밀번호를 맞혀 보지 못하게).
    잠겨 있으면 429 ACCOUNT_LOCKED. 성공하면 그 (아이디, IP) 의 실패 기록을 지운다.
    """
    login_guard.ensure_not_locked(db, user.username, ip)
    if not verify_password(current_password, user.password_hash):
        login_guard.record_failure(db, user.username, ip)
        raise AppException(ErrorCode.WRONG_PASSWORD)
    validate_password(new_password)
    if new_password == current_password:
        raise AppException(ErrorCode.INVALID_PASSWORD, "새 비밀번호는 현재 비밀번호와 달라야 합니다")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    login_guard.clear(db, user.username, ip)
    db.commit()
    _audit(user, "change_own_password", user)
    return user


# ---------------------------------------------------------------------------
# 관리자 계정 관리
# ---------------------------------------------------------------------------
def create_user(db: Session, actor: User, *, username: str, name: str, role: Role, password: str) -> User:
    """POST /users. 아이디 중복이면 409 USERNAME_TAKEN. 만든 계정은 must_change_password=true. commit 까지 한다."""
    validate_password(password)
    if db.scalar(select(User.id).where(func.lower(User.username) == username.lower())) is not None:
        raise AppException(ErrorCode.USERNAME_TAKEN)
    user = User(username=username, name=name, role=role, password_hash=hash_password(password),
                is_active=True, must_change_password=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 같은 아이디로 동시에 두 요청이 온 경우
        db.rollback()
        raise AppException(ErrorCode.USERNAME_TAKEN) from None
    _audit(actor, "create_user", user, f"role={role.value}")
    return user


def _ensure_other_active_admin(db: Session, target: User) -> None:
    """target 을 빼고도 활성 ADMIN 이 남는지 본다. 동시에 두 요청이 와도 둘 다 통과하지 않도록 행을 잠근다."""
    admins = db.scalars(
        select(User.id).where(User.role == Role.ADMIN, User.is_active.is_(True)).with_for_update()
    ).all()
    if not any(admin_id != target.id for admin_id in admins):
        raise AppException(ErrorCode.LAST_ADMIN)


def change_role(db: Session, actor: User, user_id: int, role: Role) -> User:
    """PATCH /users/{id}/role. 본인을 USER 로 낮추면 409 CANNOT_CHANGE_SELF, 마지막 활성 ADMIN 이면 409 LAST_ADMIN."""
    target = get_user(db, user_id)
    if target.role == role:
        return target
    if role != Role.ADMIN:  # ADMIN → USER (낮추기)
        if target.id == actor.id:
            raise AppException(ErrorCode.CANNOT_CHANGE_SELF)
        if target.is_active:
            _ensure_other_active_admin(db, target)
    before = target.role
    target.role = role
    db.commit()
    _audit(actor, "change_role", target, f"{before.value}->{role.value}")
    return target


def set_active(db: Session, actor: User, user_id: int, is_active: bool) -> User:
    """PATCH /users/{id}/active. 본인 비활성화는 409 CANNOT_CHANGE_SELF, 마지막 활성 ADMIN 이면 409 LAST_ADMIN."""
    target = get_user(db, user_id)
    if target.is_active == is_active:
        return target
    if not is_active:
        if target.id == actor.id:
            raise AppException(ErrorCode.CANNOT_CHANGE_SELF)
        if target.role == Role.ADMIN:
            _ensure_other_active_admin(db, target)
    target.is_active = is_active
    db.commit()
    _audit(actor, "activate" if is_active else "deactivate", target)
    return target


def reset_password(db: Session, actor: User, user_id: int, new_password: str) -> User:
    """POST /users/{id}/reset-password. 관리자가 정한 임시 비밀번호로 바꾸고 must_change_password=true. commit 까지 한다."""
    target = get_user(db, user_id)
    validate_password(new_password)
    target.password_hash = hash_password(new_password)
    target.must_change_password = True
    login_guard.clear(db, target.username)  # 모든 IP 의 잠금을 푼다 (관리자 잠금 해제 방법)
    db.commit()
    _audit(actor, "reset_password", target)
    return target
