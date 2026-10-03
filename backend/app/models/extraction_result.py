"""[담당: 장수민] extraction_results 테이블 — 추출·판정 결과 JSON (명세 2.1) 을 JSONB 로 저장.

문서 1건에 결과 1건 (document_id unique). 항목 수정 시 result 를 통째로 갱신한다.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col


class ExtractionResult(Base):
    __tablename__ = "extraction_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    result: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 2.5 표에는 없음, 재판정 시각

    document: Mapped["Document"] = relationship(back_populates="extraction")  # noqa: F821
