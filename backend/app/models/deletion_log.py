"""[담당: 홍채령] deletion_logs 테이블 — 문서 삭제 기록 (운영 정책 1장).

"누가, 언제, 무엇을, 왜 지웠는지" 와 삭제 직전의 처분·검수 이력 요약을 남긴다.
문서가 지워진 뒤에도 남아야 하므로 document_id 에 FK 를 걸지 않는다. 이 테이블을 지우는 API 는 없다.
문서 내용(추출 값)은 넣지 않는다. 검수 요약에는 횟수, 시각, 수정한 항목 이름만 넣는다.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DeletionRule
from app.db.base import Base, enum_check, str_enum


class DeletionLog(Base):
    __tablename__ = "deletion_logs"
    __table_args__ = (enum_check("rule", DeletionRule),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # 무엇을: 지운 문서의 식별 정보 (FK 없음. 연결 안 된 파일 정리처럼 문서가 없으면 null)
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    material_code: Mapped[str | None] = mapped_column(String(32))
    supplier: Mapped[str | None] = mapped_column(String(200))
    lot_no: Mapped[str | None] = mapped_column(String(100), index=True)
    received_lot_no: Mapped[str | None] = mapped_column(String(100))
    batch_id: Mapped[str | None] = mapped_column(String(36))
    status_at_delete: Mapped[str | None] = mapped_column(String(32))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 누가, 언제, 왜 (자동 정리면 deleted_by 는 null)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rule: Mapped[DeletionRule] = mapped_column(str_enum(DeletionRule, "deletion_rule"), nullable=False)
    # 삭제 직전 이력 요약
    approval_summary: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    review_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
