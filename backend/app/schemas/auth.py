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
