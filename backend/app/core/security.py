"""[담당: 홍채령] 비밀번호 해시, JWT 발급·검증"""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """해시 형식이 잘못된 경우도 불일치로 본다."""
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        return False


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
