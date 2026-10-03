"""[담당: 장수민] item_mappings 테이블 — 협력사 항목명 → 사내 표준 항목명 사전 (명세 2.5).

같은 material_code 안에서 raw_name 은 하나만 둔다 (manual 수정 시 덮어쓰기, 명세 4.9).
"""
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ItemMappingSource
from app.db.base import Base, enum_check, created_at_col, str_enum


class ItemMapping(Base):
    __tablename__ = "item_mappings"
    __table_args__ = (enum_check("source", ItemMappingSource), UniqueConstraint("material_code", "raw_name"))

    id: Mapped[int] = mapped_column(primary_key=True)
    material_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    raw_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[ItemMappingSource] = mapped_column(str_enum(ItemMappingSource, "item_mapping_source"), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()
