"""[담당: 장수민] spec_items 테이블 — 사내 규격 항목 (명세 2.5, v1.4안).

규격 세트(spec_sets) 1개에 항목 여러 개가 속한다. 세트 안에서 item_name 은 유일하다.
원자재·등급 정보는 세트에 있으므로 이 테이블에는 두지 않는다 (v1.3 의 material_code, material_name, grade 컬럼 제거).

is_required (v1.4안)
  - True  : CoA 에 없으면 누락(missing) 항목을 만든다. 기본값
  - False : CoA 에 없어도 누락으로 보지 않는다. DEMO-R 세트처럼 "별도 성적서 항목"(Mg, 자성이물 등)을 둘 때 쓴다
"""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SpecType
from app.db.base import Base, enum_check, str_enum
from app.models.user import User


class SpecItem(Base):
    __tablename__ = "spec_items"
    __table_args__ = (
        enum_check("spec_type", SpecType),
        UniqueConstraint("spec_set_id", "item_name"),
        CheckConstraint("lsl IS NULL OR usl IS NULL OR lsl <= usl", name="lsl_le_usl"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    spec_set_id: Mapped[int] = mapped_column(
        ForeignKey("spec_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 사내 표준 항목명 (= 추출 결과 normalized_name)
    unit: Mapped[str | None] = mapped_column(String(20))
    lsl: Mapped[float | None] = mapped_column(Float)
    usl: Mapped[float | None] = mapped_column(Float)
    spec_type: Mapped[SpecType] = mapped_column(str_enum(SpecType, "spec_type"), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    source: Mapped[str | None] = mapped_column(String(100))  # 항목별 기준값 근거. 예: YS/T 582-2023 D1
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    spec_set: Mapped["SpecSet"] = relationship(back_populates="items")  # noqa: F821
    updater: Mapped[User | None] = relationship()
