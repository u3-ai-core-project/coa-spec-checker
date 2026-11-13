"""[담당: 장수민] reissue_decisions 테이블 — 같은 로트 CoA 가 여러 개일 때 담당자가 고른 기준 버전 (운영 정책 8.2).

로트 묶음은 (원자재, 정규화한 로트번호) 로 정한다. 기준 버전을 고른 뒤 같은 로트의 새 CoA 가 또 들어오면
그 문서의 업로드 시각이 이 선택보다 늦으므로 다시 선택해야 한다 (app/services/reissue_service.py).
"""
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col
from app.models.user import User


class ReissueDecision(Base):
    __tablename__ = "reissue_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_code: Mapped[str] = mapped_column(String(32), nullable=False)
    lot_key: Mapped[str] = mapped_column(String(100), nullable=False)   # normalize_lot 한 로트번호
    base_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped[User] = relationship()
