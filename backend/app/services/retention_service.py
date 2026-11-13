"""[담당: 홍채령] 보관 기간과 보관용 폴더 이동 (운영 정책 1장).

- 처분 완료 문서는 처분일(재처분이면 재처분일)부터 RETENTION_YEARS 년 동안 삭제하지 않는다.
  만료 시각(retention_until)은 처분할 때 approval_service 가 정한다
- 보관 기간이 지나도 처분 완료 원본은 지우지 않는다. 보관용 폴더(ARCHIVE_DIR)로 옮기는 것만 한다 (ADMIN)
"""
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.enums import DocumentStatus
from app.core.errors import AppException, ErrorCode
from app.models import Document, User
from app.services import storage_service

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """현재 시각 (UTC). 테스트에서 바꿔 끼워 시간을 조절한다."""
    return datetime.now(timezone.utc)


def _expired_conditions(now: datetime):
    return (
        Document.status == DocumentStatus.APPROVED,
        Document.retention_until.is_not(None),
        Document.retention_until <= now,
        Document.archived_at.is_(None),
    )


def list_expired(db: Session, *, page: int, size: int) -> tuple[int, list[Document]]:
    """보관 기간이 지났고 아직 옮기지 않은 처분 완료 문서. 만료가 오래된 것부터."""
    conditions = _expired_conditions(_now())
    total = db.scalar(select(func.count()).select_from(Document).where(*conditions))
    rows = db.scalars(
        select(Document)
        .where(*conditions)
        .options(joinedload(Document.uploader), joinedload(Document.approver), joinedload(Document.extraction))
        .order_by(Document.retention_until, Document.id)
        .offset((page - 1) * size)
        .limit(size)
    ).unique()
    return total, list(rows)


def _archive_dir() -> Path:
    path = Path(settings.ARCHIVE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)  # 서버 계정만 읽고 쓸 수 있게
    except OSError:
        pass
    return path


def archive_document(db: Session, document_id: str, actor: User) -> Document:
    """POST /documents/{id}/archive. 원본 파일을 보관용 폴더로 옮긴다. commit 까지 한다.

    - 문서 없음: 404 DOCUMENT_NOT_FOUND
    - 처분 완료가 아님: 409 NOT_APPROVED
    - 이미 옮김: 409 ALREADY_ARCHIVED
    - 보관 기간이 아직 안 지남: 409 RETENTION_NOT_EXPIRED
    파일을 먼저 옮기고 DB 를 바꾼다. DB 저장이 실패하면 파일을 원래 자리로 되돌린다.
    """
    doc = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    if doc.status != DocumentStatus.APPROVED:
        raise AppException(ErrorCode.NOT_APPROVED, "처분 완료 문서만 보관용 폴더로 옮길 수 있습니다")
    if doc.archived_at is not None:
        raise AppException(ErrorCode.ALREADY_ARCHIVED)
    if doc.retention_until is None or doc.retention_until > _now():
        until = doc.retention_until.date().isoformat() if doc.retention_until else "미정"
        raise AppException(ErrorCode.RETENTION_NOT_EXPIRED,
                           f"보관 기간({until}까지)이 지나야 보관용 폴더로 옮길 수 있습니다")

    source = Path(doc.file_path)
    if not source.is_file():
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND, "원본 파일을 찾을 수 없습니다")
    target = _archive_dir() / source.name  # 저장 이름(문서 ID + 확장자)을 그대로 쓴다
    shutil.move(str(source), str(target))
    try:
        doc.file_path = str(target)
        doc.archived_at = func.now()
        db.commit()
    except Exception:
        db.rollback()
        shutil.move(str(target), str(source))
        raise
    db.refresh(doc)
    storage_service.invalidate()  # 업로드 폴더에서 빠졌으므로 저장 공간을 다시 잰다
    logger.info("보관용 폴더로 이동: document_id=%s actor_id=%s", doc.id, actor.id)
    return doc
