"""[담당: 홍채령] GET /users (명세 4.3), 관리자 계정 관리 (운영 정책 2단계, 명세 추가 예정)

- GET   /users                       계정 목록 (비활성 계정 포함)
- POST  /users                       계정 만들기 (초기 비밀번호, 첫 로그인 때 변경 필요)
- PATCH /users/{id}/role             권한 바꾸기
- PATCH /users/{id}/active           활성화·비활성화 (삭제 대신)
- POST  /users/{id}/reset-password   비밀번호 초기화 (임시 비밀번호, 첫 로그인 때 변경 필요)

모두 ADMIN 전용이다.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.user import (
    PasswordResetRequest, UserActiveUpdate, UserAdminItem, UserCreateRequest, UserRoleUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


def _item(user: User) -> UserAdminItem:
    return UserAdminItem.model_validate(user)


@router.get("", response_model=ApiResponse[list[UserAdminItem]])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """대시보드 관리자 뷰의 담당자 필터 목록, 계정 관리 화면 목록."""
    return ok([_item(u) for u in user_service.list_users(db)])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[UserAdminItem])
def create_user(body: UserCreateRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = user_service.create_user(db, admin, username=body.username, name=body.name, role=body.role,
                                    password=body.password)
    return ok(_item(user))


@router.patch("/{user_id}/role", response_model=ApiResponse[UserAdminItem])
def change_role(user_id: int, body: UserRoleUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    return ok(_item(user_service.change_role(db, admin, user_id, body.role)))


@router.patch("/{user_id}/active", response_model=ApiResponse[UserAdminItem])
def set_active(user_id: int, body: UserActiveUpdate, db: Session = Depends(get_db),
               admin: User = Depends(require_admin)):
    return ok(_item(user_service.set_active(db, admin, user_id, body.is_active)))


@router.post("/{user_id}/reset-password", response_model=ApiResponse[UserAdminItem])
def reset_password(user_id: int, body: PasswordResetRequest, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    return ok(_item(user_service.reset_password(db, admin, user_id, body.new_password)))
