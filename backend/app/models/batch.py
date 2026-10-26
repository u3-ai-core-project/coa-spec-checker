"""[담당: 장수민] batches, receipts 테이블 — 일괄 접수 (멘토님 범위 정의서 UC01·UC07, 명세 v1.4 4.4-1).

batches  : 한 번에 올린 CoA 묶음 (최대 20건). 문서는 documents.batch_id 로 연결한다.
receipts : 같이 올린 입고 정보 CSV 의 행 (receipt_id, supplier, material, received_lot, spec_id, received_date).
           CoA 와는 CSV 의 file_name 열로 바로 연결하거나, 없으면 추출된 CoA 로트번호 = received_lot 으로 연결한다.
           document_id 가 비어 있으면 아직 CoA 가 연결되지 않은 입고 건이다 (CoA 미접수).
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col
from app.models.user import User


def _uuid() -> str:
    return str(uuid.uuid4())


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    material_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = created_at_col()

    creator: Mapped[User] = relationship()
    receipts: Mapped[list["Receipt"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="Receipt.id"
    )


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("batch_id", "receipt_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_id: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(200))
    material_code: Mapped[str] = mapped_column(String(32), nullable=False)
    received_lot_no: Mapped[str] = mapped_column(String(100), nullable=False)
    spec_set_code: Mapped[str | None] = mapped_column(String(64))
    received_date: Mapped[date | None] = mapped_column(Date)
    file_name: Mapped[str | None] = mapped_column(String(255))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = created_at_col()

    batch: Mapped[Batch] = relationship(back_populates="receipts")
