"""[담당: 홍채령] users 테이블 (명세 2.5).

다른 테이블 FK 와 첫 마이그레이션 때문에 명세 컬럼만 먼저 넣어 두었다. 이후 수정은 홍채령.
"""
from datetime import datetime

from sqlalchemy import String
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
    created_at: Mapped[datetime] = created_at_col()
