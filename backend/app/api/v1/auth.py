"""[담당: 홍채령] POST /auth/login, GET /auth/me (명세 4.1, 4.2)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.response import ok
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.common import ApiResponse
from app.schemas.user import UserMe, UserSummary
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = user_service.authenticate(db, body.username, body.password)
    return ok(
        LoginResponse(
            access_token=create_access_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserSummary.model_validate(user),
        )
    )


@router.get("/me", response_model=ApiResponse[UserMe])
def me(user: User = Depends(get_current_user)):
    return ok(UserMe.model_validate(user))
