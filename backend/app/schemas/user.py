"""[담당: 홍채령] 사용자 요청·응답"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Role
from app.schemas.common import ORMModel


class UserSummary(ORMModel):
    """로그인 응답의 user (명세 4.1)."""
    id: int
    name: str
    role: Role


class UserMe(ORMModel):
    """GET /auth/me (명세 4.2). is_active, must_change_password 는 운영 정책 2단계 추가."""
    id: int
    username: str
    name: str
    role: Role
    is_active: bool
    must_change_password: bool


class UserAdminItem(ORMModel):
    """GET /users 목록 항목, 관리자 계정 API 응답 (명세 4.3 + 운영 정책 2단계)."""
    id: int
    username: str
    name: str
    role: Role
    is_active: bool
    must_change_password: bool
    created_at: datetime


class UserCreateRequest(BaseModel):
    """POST /users. 초기 비밀번호는 비밀번호 규칙을 따른다. 만든 계정은 첫 로그인 때 비밀번호를 바꿔야 한다."""
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$",
                          description="영문·숫자·._- 3~50자")
    name: str = Field(min_length=1, max_length=50)
    role: Role = Role.USER
    password: str = Field(description="초기 비밀번호")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("이름을 입력해야 합니다")
        return v


class UserRoleUpdate(BaseModel):
    role: Role


class UserActiveUpdate(BaseModel):
    is_active: bool


class PasswordResetRequest(BaseModel):
    """POST /users/{id}/reset-password. 관리자가 정한 임시 비밀번호."""
    new_password: str


class PasswordChangeRequest(BaseModel):
    """POST /auth/password. 로그인한 본인의 비밀번호 변경."""
    current_password: str
    new_password: str
