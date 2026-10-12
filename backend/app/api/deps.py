"""[담당: 홍채령] 인증·권한 의존성 — 두 사람의 접점.

장수민 쪽 API 는 아래 두 함수의 '시그니처'에만 의존한다. 본문 구현은 홍채령.

    @router.post("/{id}/cancel-approval")
    def cancel(id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)): ...

    @router.post("/{id}/approve")
    def approve(id: str, user: User = Depends(get_current_user), ...): ...
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppException, ErrorCode
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """토큰 검증 후 User 반환. 토큰 없음·만료·위조면 AppException(UNAUTHORIZED)."""
    if credentials is None:
        raise AppException(ErrorCode.UNAUTHORIZED)
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:  # 토큰은 유효하지만 사용자가 삭제된 경우 포함
        raise AppException(ErrorCode.UNAUTHORIZED)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise AppException(ErrorCode.FORBIDDEN)
    return user
