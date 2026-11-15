"""[담당: 장수민] documents 테이블 (명세 2.5, 2.6, 2.7).

문서 상태의 기준은 이 테이블의 status 다. JSON 의 review_status 는 동기화용 사본.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DocumentStatus, ErrorKind, FinalDecision, LotRecommendation
from app.db.base import Base, enum_check, str_enum
from app.models.user import User


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        enum_check("status", DocumentStatus),
        enum_check("lot_recommendation", LotRecommendation),
        enum_check("final_decision", FinalDecision),
        enum_check("error_kind", ErrorKind),
    )

    # 명세에서 document_id 가 string 이라 UUID 문자열로 둔다
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # 파일
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)       # 명세 4.5 응답용 (2.5 표에는 없음)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)   # 4.7 원본 파일 응답용 (2.5 표에는 없음)
    # 파일 고유값 (SHA-256). 같은 파일을 다시 올리면 경고하는 데 쓴다 (운영 정책 1장). 기존 파일을 못 읽으면 null
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # 같은 파일이 이미 있는데 담당자가 확인하고 다시 접수한 경우, 그때 있던 문서 (참고용, 그 문서가 지워지면 null)
    duplicate_of: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))

    # 업로드 시 입력
    material_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    supplier: Mapped[str | None] = mapped_column(String(200))
    received_lot_no: Mapped[str | None] = mapped_column(String(100))

    # 추출 결과에서 채움
    material_name: Mapped[str | None] = mapped_column(String(100))
    po_no: Mapped[str | None] = mapped_column(String(100))  # 시연용 목업
    lot_no: Mapped[str | None] = mapped_column(String(100), index=True)
    test_date: Mapped[date | None] = mapped_column(Date)
    origin: Mapped[str | None] = mapped_column(String(100))
    applied_standard: Mapped[str | None] = mapped_column(String(100))

    # 이 문서를 판정한 사내 규격 세트 (v1.4안). 업로드 때 정한다.
    # 지정하지 않으면 원자재 기본 세트. 규격 세트가 바뀌어도 어떤 기준으로 판정했는지 남기기 위해 둔다.
    spec_set_id: Mapped[int | None] = mapped_column(ForeignKey("spec_sets.id"), index=True)
    # 일괄 접수(UC01)로 올린 문서면 그 묶음. 한 건씩 올리면 null
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id", ondelete="SET NULL"), index=True)

    # 상태와 판정
    status: Mapped[DocumentStatus] = mapped_column(
        str_enum(DocumentStatus, "document_status"), nullable=False, default=DocumentStatus.QUEUED, index=True
    )
    lot_recommendation: Mapped[LotRecommendation | None] = mapped_column(
        str_enum(LotRecommendation, "lot_recommendation")
    )
    final_decision: Mapped[FinalDecision | None] = mapped_column(str_enum(FinalDecision, "final_decision"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    # 처리 실패·재시도 기록 (운영 정책 4장). 담당자가 원인을 알고, 자동 재시도 상한을 셀 수 있게 한다.
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_stage: Mapped[str | None] = mapped_column(String(32))
    error_kind: Mapped[ErrorKind | None] = mapped_column(str_enum(ErrorKind, "error_kind"))
    # 추출이 실제로 작동한 시간 (운영 정책 7장). 마지막 시도의 시작·종료 시각
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 사람과 시각
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 보관 기간 만료 시각 (운영 정책 1장). 처분할 때 approved_at + RETENTION_YEARS 로 정하고, 처분 취소하면 비운다.
    # 처분할 때 값을 박아 두므로 RETENTION_YEARS 를 바꿔도 이미 처분한 문서의 기간은 그대로다
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 보관 기간이 지나 원본을 보관용 폴더(ARCHIVE_DIR)로 옮긴 시각. 옮긴 뒤에도 원본 조회는 된다
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 방치 문서 (운영 정책 1장). 마지막 활동 = 업로드, 값·항목명 수정, 항목 확인, 규격 세트 변경, 처분·보류·취소 (조회는 제외)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                       nullable=False)
    # 처분 전인데 STALE_DAYS 동안 활동이 없어 방치로 표시한 시각. 활동하면 비운다
    stale_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    uploader: Mapped[User] = relationship(foreign_keys=[uploaded_by])
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by])
    spec_set: Mapped["SpecSet | None"] = relationship()  # noqa: F821
    extraction: Mapped["ExtractionResult | None"] = relationship(  # noqa: F821
        back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
