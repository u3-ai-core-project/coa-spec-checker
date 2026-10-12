"""[담당: 장수민] spec_items 테이블 — 사내 규격 (명세 2.5).

material_code + item_name 조합으로 규격을 식별한다.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SpecType
from app.db.base import Base, enum_check, str_enum
from app.models.user import User


class SpecItem(Base):
    __tablename__ = "spec_items"
    __table_args__ = (
        enum_check("spec_type", SpecType),
        UniqueConstraint("material_code", "item_name"),
        CheckConstraint("lsl IS NULL OR usl IS NULL OR lsl <= usl", name="lsl_le_usl"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 예: LI2CO3
    material_name: Mapped[str] = mapped_column(String(100), nullable=False)              # 예: 탄산리튬
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)                  # 사내 표준 항목명
    unit: Mapped[str | None] = mapped_column(String(20))
    lsl: Mapped[float | None] = mapped_column(Float)
    usl: Mapped[float | None] = mapped_column(Float)
    spec_type: Mapped[SpecType] = mapped_column(str_enum(SpecType, "spec_type"), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(20))    # 예: D1
    source: Mapped[str | None] = mapped_column(String(100))  # 예: YS/T 582-2023 D1
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    updater: Mapped[User | None] = relationship()
