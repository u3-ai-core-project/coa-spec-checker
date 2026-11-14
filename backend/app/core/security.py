"""[담당: 홍채령] 비밀번호 해시, JWT 발급·검증"""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import AppException, ErrorCode

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """해시 형식이 잘못된 경우도 불일치로 본다."""
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        return False


PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # bcrypt 는 72바이트까지만 본다. 넘는 부분은 무시되므로 아예 받지 않는다


def validate_password(password: str) -> None:
    """비밀번호 규칙 (운영 정책 2단계). 맞지 않으면 400 INVALID_PASSWORD 와 이유를 알려 준다.

    - 8자 이상
    - 영문자(A-Z, a-z) 1개 이상, 숫자 1개 이상
    - UTF-8 로 72바이트 이하 (한글은 1글자에 3바이트)
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise AppException(ErrorCode.INVALID_PASSWORD, f"비밀번호는 {PASSWORD_MIN_LENGTH}자 이상이어야 합니다")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise AppException(ErrorCode.INVALID_PASSWORD, "비밀번호가 너무 깁니다 (영문 기준 72자 이하)")
    if not any(c.isascii() and c.isalpha() for c in password):
        raise AppException(ErrorCode.INVALID_PASSWORD, "비밀번호에 영문자를 하나 이상 넣어야 합니다")
    if not any(c.isdigit() and c.isascii() for c in password):
        raise AppException(ErrorCode.INVALID_PASSWORD, "비밀번호에 숫자를 하나 이상 넣어야 합니다")


def create_access_token(user_id: int) -> str:
    """sub 에 사용자 id, exp 에 만료 시각(ACCESS_TOKEN_EXPIRE_MINUTES 후)을 넣는다."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """유효한 토큰이면 사용자 id, 만료·위조·형식 오류면 None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None
