"""[담당: 홍채령] POST /auth/login, GET /auth/me (명세 4.1, 4.2), POST /auth/password (운영 정책 2단계)

GET /auth/me 와 POST /auth/password 는 비밀번호를 바꿔야 하는 계정(must_change_password)도 쓸 수 있다.

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_authenticated_user
from app.core.config import settings
from app.core.response import ok
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.common import ApiResponse
from app.schemas.user import PasswordChangeRequest, UserMe, UserSummary
from app.services import login_guard, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """5번 연속 틀리면 15분 잠금 (운영 정책 3단계): 429 ACCOUNT_LOCKED, Retry-After 헤더에 남은 초."""
    user = user_service.authenticate(db, body.username, body.password, login_guard.client_ip(request))
    return ok(
        LoginResponse(
            access_token=create_access_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserSummary.model_validate(user),
            must_change_password=user.must_change_password,
        )
    )


@router.get("/me", response_model=ApiResponse[UserMe])
def me(user: User = Depends(get_authenticated_user)):
    return ok(UserMe.model_validate(user))


@router.post("/password", response_model=ApiResponse[UserMe])
def change_password(body: PasswordChangeRequest, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_authenticated_user)):
    """로그인한 본인의 비밀번호 변경. 성공하면 must_change_password 가 false 가 된다. 토큰은 그대로 쓴다."""
    user = user_service.change_own_password(db, user, body.current_password, body.new_password,
                                            login_guard.client_ip(request))
    return ok(UserMe.model_validate(user))
