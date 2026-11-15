"""[담당: 장수민] spec_change_logs 테이블 — 사내 규격 항목 변경 이력 (명세 v1.4 2.5, 4.21).

규격을 바꾸면 판정 결과가 달라지므로, 누가 언제 왜 바꿨는지 남긴다 (규격 관리 화면 5-1 의 변경 이력).
before_value / after_value 는 실제로 바뀐 필드만 담은 문자열이다. 예) "usl: 50" → "usl: 30"
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col
from app.models.user import User


class SpecChangeLog(Base):
    __tablename__ = "spec_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    spec_item_id: Mapped[int] = mapped_column(
        ForeignKey("spec_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    before_value: Mapped[str] = mapped_column(Text, nullable=False)
    after_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped[User] = relationship()
