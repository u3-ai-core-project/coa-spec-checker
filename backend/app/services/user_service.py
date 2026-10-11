"""[담당: 홍채령] 로그인 인증, 사용자 조회."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppException, ErrorCode
from app.core.security import verify_password
from app.models import User


def authenticate(db: Session, username: str, password: str) -> User:
    """아이디·비밀번호가 맞으면 User, 아니면 401 INVALID_CREDENTIALS (어느 쪽이 틀렸는지 구분하지 않음)."""
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise AppException(ErrorCode.INVALID_CREDENTIALS)
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))
