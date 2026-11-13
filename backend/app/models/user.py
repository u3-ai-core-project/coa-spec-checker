"""[담당: 홍채령] users 테이블 (명세 2.5).

다른 테이블 FK 와 첫 마이그레이션 때문에 명세 컬럼만 먼저 넣어 두었다. 이후 수정은 홍채령.
"""
from datetime import datetime

from sqlalchemy import Boolean, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Role
from app.db.base import Base, enum_check, created_at_col, str_enum


class User(Base):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", Role),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), nullable=False, default=Role.USER)
    # 운영 정책 2단계: 계정은 지우지 않고 비활성화한다. 비활성 계정은 로그인·기존 토큰 모두 막힌다
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    # 관리자가 만들거나 비밀번호를 초기화한 계정은 첫 로그인 때 비밀번호를 바꿔야 한다
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = created_at_col()
