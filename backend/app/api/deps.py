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


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """토큰만 검증한다 (비밀번호 변경 필요 여부는 보지 않음). GET /auth/me, POST /auth/password 전용.

    토큰 없음·만료·위조, 사용자 없음, 비활성 계정이면 401 UNAUTHORIZED.
    비활성화하면 이미 발급된 토큰도 바로 쓸 수 없게 된다 (운영 정책 2단계).
    """
    if credentials is None:
        raise AppException(ErrorCode.UNAUTHORIZED)
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:  # 토큰은 유효하지만 사용자가 삭제된 경우 포함
        raise AppException(ErrorCode.UNAUTHORIZED)
    if not user.is_active:
        raise AppException(ErrorCode.UNAUTHORIZED, "비활성화된 계정입니다. 관리자에게 문의하세요")
    return user


def get_current_user(user: User = Depends(get_authenticated_user)) -> User:
    """토큰 검증 후 User 반환. 나머지 모든 API 가 쓴다.

    - 토큰 문제·비활성 계정: 401 UNAUTHORIZED (get_authenticated_user)
    - 비밀번호를 바꿔야 하는 계정(must_change_password): 403 PASSWORD_CHANGE_REQUIRED.
      이때 쓸 수 있는 API 는 로그인, GET /auth/me, POST /auth/password 뿐이다
    """
    if user.must_change_password:
        raise AppException(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise AppException(ErrorCode.FORBIDDEN)
    return user
