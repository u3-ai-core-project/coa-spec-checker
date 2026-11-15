"""[담당: 홍채령] 자동 정리와 방치 문서 표시 (운영 정책 1장).

자동으로 지우는 것은 업무 기록이 되기 전의 데이터 두 가지뿐이다.
  (a) 추출에 실패한(failed) 뒤 FAILED_RETENTION_DAYS 일 지난 문서 → 삭제 기록(rule=auto_failed_7d)을 남기고 삭제
  (b) 업로드 폴더에 있지만 어떤 문서와도 연결되지 않은 파일 중 ORPHAN_FILE_HOURS 시간 지난 것
      → 삭제 기록(rule=auto_orphan_file, document_id 없음)을 남기고 삭제
그 밖에는 아무것도 지우지 않는다. 보관용 폴더(ARCHIVE_DIR)는 건드리지 않는다.

  (c) 처분 전 문서가 STALE_DAYS 일 동안 활동이 없으면 방치로 표시한다(stale_notified_at). 지우지 않는다.
      표시된 문서는 올린 사람이 문서 목록(stale=true)에서 보고, STALE_GRACE_DAYS 일이 더 지나면 관리자 목록에 오른다.
      삭제는 사람이 사유를 넣어 직접 한다 (DELETE /documents/{id}).

run_cleanup() 은 몇 번을 돌려도 결과가 같다 (이미 지운 것·표시한 것은 다시 대상이 되지 않는다).
서버 1대 운영 전제: main.py 의 스레드가 주기적으로 부르고, 관리자는 POST /admin/cleanup/run 으로 바로 돌릴 수 있다.
"""
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import DeletionRule, DocumentStatus
from app.models import DeletionLog, Document
from app.services import deletion_service

logger = logging.getLogger(__name__)

REASON_FAILED = "추출 실패 후 {days}일이 지나 자동 삭제 (운영 정책 1장)"
REASON_ORPHAN = "어떤 문서와도 연결되지 않은 업로드 파일이 {hours}시간 지나 자동 삭제 (운영 정책 1장)"
# 방치 대상: 추출이 끝났고 아직 처분되지 않은 문서. 대기·추출 중·실패·처분 완료는 제외
STALE_STATUSES = (DocumentStatus.EXTRACTED, DocumentStatus.IN_REVIEW, DocumentStatus.ON_HOLD)


@dataclass
class CleanupResult:
    dry_run: bool
    failed_documents_deleted: list[str] = field(default_factory=list)
    orphan_files_deleted: list[str] = field(default_factory=list)
    stale_documents_marked: list[str] = field(default_factory=list)


def _now() -> datetime:
    """현재 시각 (UTC). 테스트에서 바꿔 끼워 시간을 조절한다."""
    return datetime.now(timezone.utc)


def _failed_targets(db: Session, now: datetime) -> list[Document]:
    cutoff = now - timedelta(days=settings.FAILED_RETENTION_DAYS)
    failed_at = func.coalesce(Document.processing_finished_at, Document.uploaded_at)
    return list(db.scalars(
        select(Document).where(Document.status == DocumentStatus.FAILED, failed_at < cutoff).order_by(Document.id)
    ))


def _orphan_targets(db: Session, now: datetime) -> list[Path]:
    upload_dir = Path(settings.UPLOAD_DIR)
    if not upload_dir.is_dir():
        return []
    known = {Path(p).name for p in db.scalars(select(Document.file_path))}
    cutoff = (now - timedelta(hours=settings.ORPHAN_FILE_HOURS)).timestamp()
    targets = []
    for entry in os.scandir(upload_dir):
        if not entry.is_file(follow_symlinks=False) or entry.name.startswith("."):
            continue  # 폴더·링크·숨김 파일(.gitkeep 등)은 건드리지 않는다
        if entry.name in known:
            continue
        if entry.stat(follow_symlinks=False).st_mtime < cutoff:
            targets.append(Path(entry.path))
    return sorted(targets)


def _stale_targets(db: Session, now: datetime) -> list[Document]:
    cutoff = now - timedelta(days=settings.STALE_DAYS)
    return list(db.scalars(
        select(Document).where(Document.status.in_(STALE_STATUSES), Document.stale_notified_at.is_(None),
                               Document.last_activity_at < cutoff).order_by(Document.id)
    ))


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def run_cleanup(db: Session, *, dry_run: bool = False) -> CleanupResult:
    """자동 정리 한 번. dry_run 이면 대상만 돌려주고 아무것도 바꾸지 않는다."""
    now = _now()
    result = CleanupResult(dry_run=dry_run)

    # (a) 실패 7일 지난 문서
    for doc in _failed_targets(db, now):
        result.failed_documents_deleted.append(doc.id)
        if dry_run:
            continue
        _, path = deletion_service.delete_with_log(
            db, doc, actor_id=None, reason=REASON_FAILED.format(days=settings.FAILED_RETENTION_DAYS),
            rule=DeletionRule.AUTO_FAILED_7D)
        db.commit()
        deletion_service.remove_file(path)

    # (b) 연결 안 된 파일 (실패 문서를 지운 뒤에 본다. 그 문서 파일은 이미 같이 지워졌다)
    for path in _orphan_targets(db, now):
        result.orphan_files_deleted.append(path.name)
        if dry_run:
            continue
        db.add(DeletionLog(
            document_id=None, file_name=path.name, file_size=path.stat().st_size, file_sha256=_sha256(path),
            deleted_by=None, reason=REASON_ORPHAN.format(hours=settings.ORPHAN_FILE_HOURS),
            rule=DeletionRule.AUTO_ORPHAN_FILE, approval_summary=[], review_summary={},
        ))
        db.commit()
        deletion_service.remove_file(path)

    # (c) 방치 문서 표시
    stale = _stale_targets(db, now)
    result.stale_documents_marked = [d.id for d in stale]
    if not dry_run and stale:
        for doc in stale:
            doc.stale_notified_at = now
        db.commit()

    if not dry_run and (result.failed_documents_deleted or result.orphan_files_deleted or stale):
        # 문서 ID 와 개수만 남긴다 (파일 이름·문서 내용 없음)
        logger.info("자동 정리: 실패 문서 삭제 %d건 %s, 연결 안 된 파일 삭제 %d건, 방치 표시 %d건 %s",
                    len(result.failed_documents_deleted), result.failed_documents_deleted,
                    len(result.orphan_files_deleted), len(stale), result.stale_documents_marked)
    return result


def stale_overdue_conditions(now: datetime):
    """관리자 목록: 방치 표시 후 STALE_GRACE_DAYS 일이 지나도 그대로인 처분 전 문서."""
    cutoff = now - timedelta(days=settings.STALE_GRACE_DAYS)
    return (Document.status.in_(STALE_STATUSES), Document.stale_notified_at.is_not(None),
            Document.stale_notified_at <= cutoff)
