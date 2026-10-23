"""[담당: 장수민] review_logs 테이블 — 항목 수정(edit)·확인(confirm)·항목명 수정(rename) 이력 (명세 2.5).

before_value / after_value 는 정량·정성 값을 모두 담도록 문자열로 저장한다.
reason 은 수정 사유다 (v1.4). 값 수정(edit)은 필수로 받고, 항목명 수정(rename)은 선택, 확인(confirm)은 null.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReviewAction, ValueSource
from app.db.base import Base, enum_check, str_enum
from app.models.user import User


class ReviewLog(Base):
    __tablename__ = "review_logs"
    __table_args__ = (enum_check("action", ReviewAction), enum_check("value_source", ValueSource))

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[ReviewAction] = mapped_column(str_enum(ReviewAction, "review_action"), nullable=False)
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    # 값 수정(edit)일 때 입력값의 출처 (v1.4안, 명세 2.5 표에는 없음). 확인·항목명 수정이면 null
    value_source: Mapped[ValueSource | None] = mapped_column(str_enum(ValueSource, "value_source"))
    reason: Mapped[str | None] = mapped_column(Text)  # 수정 사유 (v1.4)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    reviewer: Mapped[User] = relationship()
