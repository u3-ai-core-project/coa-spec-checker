"""[담당: 홍채령] 로그인 요청·응답, 토큰"""
from pydantic import BaseModel

from app.schemas.user import UserSummary


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 초
    user: UserSummary
    must_change_password: bool = False  # true 면 POST /auth/password 로 비밀번호부터 바꿔야 한다 (운영 정책 2단계)
