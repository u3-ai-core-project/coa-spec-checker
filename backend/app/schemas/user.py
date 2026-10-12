"""[담당: 홍채령] 사용자 응답"""
from app.core.enums import Role
from app.schemas.common import ORMModel


class UserSummary(ORMModel):
    """로그인 응답의 user, GET /users 목록 항목 (명세 4.1, 4.3)."""
    id: int
    name: str
    role: Role


class UserMe(ORMModel):
    """GET /auth/me (명세 4.2)."""
    id: int
    username: str
    name: str
    role: Role
