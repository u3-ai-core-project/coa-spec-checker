"""[담당: 장수민] approval_logs 테이블 — 처분(approve)·보류(hold)·취소(cancel) 이력 (명세 2.5)."""
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ApprovalAction, FinalDecision, FollowUp
from app.db.base import Base, enum_check, created_at_col, str_enum
from app.models.user import User


class ApprovalLog(Base):
    __tablename__ = "approval_logs"
    __table_args__ = (
        enum_check("action", ApprovalAction),
        enum_check("decision", FinalDecision),
        enum_check("follow_up", FollowUp),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[ApprovalAction] = mapped_column(str_enum(ApprovalAction, "approval_action"), nullable=False)
    decision: Mapped[FinalDecision | None] = mapped_column(str_enum(FinalDecision, "approval_decision"))
    follow_up: Mapped[FollowUp | None] = mapped_column(str_enum(FollowUp, "follow_up"))  # 4.13, 4.15 용 (2.5 표에는 없음)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped[User] = relationship()
