"""[담당: 홍채령] 저장 공간 확인 (운영 정책 1장).

- 업로드 폴더(UPLOAD_DIR)에 있는 파일 크기만 센다. 보관용 폴더(ARCHIVE_DIR)는 빼서, 옮기면 자리가 생기게 한다
- 한도(STORAGE_LIMIT_GB)의 STORAGE_WARN_PERCENT% 이상이면 warn(관리자 경고), STORAGE_BLOCK_PERCENT% 이상이면 block.
  새 파일을 받으면 차단 기준을 넘게 되는 업로드는 저장 전에 507 STORAGE_FULL 로 거절한다. 조회·검수·처분은 그대로 된다
- 그 사이에도 자동으로 지우지 않는다. 대신 정리 후보를 우선순위대로 보여 준다 (admin_status)

폴더를 업로드마다 훑으면 느려서 결과를 CACHE_SECONDS 초 동안 기억한다 (서버 1대 운영 전제, 운영 정책 4장).
이 서버가 파일을 저장하면 기억한 값에 더하고, 지우거나 옮기면 기억한 값을 버려 다음에 새로 잰다.

안전장치: 업로드 폴더가 있는 디스크의 실제 남은 공간이 MIN_FREE_DISK_GB 보다 적어지면 한도와 상관없이 block 이다.
한도를 디스크보다 크게 잡았거나, DB·로그 같은 다른 것이 디스크를 먼저 채우는 경우를 막는다.
"""
import logging
import os
import shutil
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import DocumentStatus
from app.core.errors import AppException, ErrorCode
from app.models import Document

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60
MAX_IDS = 50  # 정리 후보마다 돌려줄 ID 수 (개수·크기는 전체)

_cache: dict[str, tuple[int, float]] = {}  # 업로드 폴더 경로 → (사용 바이트, 잰 시각)
_last_level: dict[str, str] = {}


def _dir() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


def _scan(path: Path) -> dict[str, int]:
    """{파일 이름: 크기}. 폴더·링크·숨김 파일은 뺀다. 폴더가 없으면 빈 dict."""
    files: dict[str, int] = {}
    if not path.is_dir():
        return files
    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False) and not entry.name.startswith("."):
            files[entry.name] = entry.stat(follow_symlinks=False).st_size
    return files


def limit_bytes() -> int:
    return int(settings.STORAGE_LIMIT_GB * 1024 ** 3)


def used_bytes(*, refresh: bool = False) -> int:
    key = str(_dir())
    cached = _cache.get(key)
    if not refresh and cached is not None and time.monotonic() - cached[1] < CACHE_SECONDS:
        return cached[0]
    used = sum(_scan(_dir()).values())
    _cache[key] = (used, time.monotonic())
    return used


def note_added(size: int) -> None:
    """업로드 폴더에 파일을 저장했을 때 기억한 값에 더한다."""
    key = str(_dir())
    if key in _cache:
        used, at = _cache[key]
        _cache[key] = (used + size, at)


def invalidate() -> None:
    """업로드 폴더에서 파일을 지우거나 옮겼을 때 기억한 값을 버린다 (다음 확인 때 새로 잰다)."""
    _cache.pop(str(_dir()), None)


def min_free_bytes() -> int:
    return int(settings.MIN_FREE_DISK_GB * 1024 ** 3)


def disk_usage() -> tuple[int, int]:
    """(디스크 전체, 남은 공간) 바이트. 업로드 폴더가 아직 없으면 가장 가까운 상위 폴더의 디스크를 본다."""
    path = _dir()
    while not path.exists() and path != path.parent:
        path = path.parent
    usage = shutil.disk_usage(path)
    return usage.total, usage.free


def _disk_low(incoming_bytes: int = 0) -> bool:
    return min_free_bytes() > 0 and disk_usage()[1] - incoming_bytes < min_free_bytes()


def _percent(used: int) -> float:
    return used * 100 / limit_bytes()


def reason_of(used: int) -> str | None:
    """block 이유: "disk"(디스크 실제 남은 공간 부족) | "quota"(설정 한도의 차단 기준 도달) | None(차단 아님)."""
    if _disk_low():
        return "disk"
    if _percent(used) >= settings.STORAGE_BLOCK_PERCENT:
        return "quota"
    return None


def level_of(used: int) -> str:
    """ok / warn / block. 디스크 실제 남은 공간이 안전 기준보다 적어도 block."""
    if _disk_low():
        return "block"
    percent = _percent(used)
    if percent >= settings.STORAGE_BLOCK_PERCENT:
        return "block"
    if percent >= settings.STORAGE_WARN_PERCENT:
        return "warn"
    return "ok"


def _log_level_change(used: int) -> str:
    """단계가 바뀔 때 한 번만 서버 로그에 숫자만 남긴다 (관리자 경고). 현재 단계를 돌려준다."""
    key, level, reason = str(_dir()), level_of(used), reason_of(used)
    state = f"{level}({reason})" if reason else level  # 예: ok, warn, block(quota), block(disk)
    previous = _last_level.get(key)
    if previous != state:
        _last_level[key] = state
        if previous is not None or level != "ok":
            logger.warning("저장 공간 단계 %s → %s: %.1f%% 사용 (%d / %d bytes), 디스크 남은 공간 %d bytes",
                           previous or "-", state, _percent(used), used, limit_bytes(), disk_usage()[1])
    return level


def ensure_capacity(incoming_bytes: int) -> None:
    """새 파일(들)을 받기 전에 부른다. 지금 block 이거나, 받으면 차단 기준에 닿으면 507 STORAGE_FULL."""
    used = used_bytes()
    _log_level_change(used)
    if (used + incoming_bytes) * 100 >= limit_bytes() * settings.STORAGE_BLOCK_PERCENT:
        raise AppException(ErrorCode.STORAGE_FULL)
    if _disk_low(incoming_bytes):
        raise AppException(ErrorCode.STORAGE_FULL, "서버 디스크의 남은 공간이 부족해 새 업로드를 받을 수 없습니다. 관리자에게 문의하세요")


def public_status() -> dict:
    """GET /storage (로그인한 모든 사용자). 업로드 화면 안내용: 단계와 사용률만."""
    used = used_bytes()
    level = _log_level_change(used)
    return {"level": level, "reason": reason_of(used), "used_percent": round(_percent(used), 1),
            "warn_percent": settings.STORAGE_WARN_PERCENT, "block_percent": settings.STORAGE_BLOCK_PERCENT}


def _group(kind: str, action: str, rows: list[tuple[str, int]]) -> dict:
    return {
        "kind": kind,
        "action": action,
        "count": len(rows),
        "bytes": sum(size for _, size in rows),
        "ids": [i for i, _ in rows[:MAX_IDS]],
    }


def admin_status(db: Session) -> dict:
    """GET /admin/storage (ADMIN). 폴더를 새로 훑고, 정리 후보를 우선순위대로 돌려준다. 아무것도 지우지 않는다.

    우선순위: (1) 연결 안 된 파일 (2) 추출 실패 문서 (3) 방치 표시 후 유예 기간이 지난 문서 (4) 방치 표시된 문서
    (5) 보관 기간이 지났는데 아직 옮기지 않은 처분 완료 문서 (삭제가 아니라 보관용 폴더 이동 대상)
    """
    # 순환 import 를 피하려고 여기서 부른다
    from app.services.cleanup_service import STALE_STATUSES, stale_overdue_conditions, _now as cleanup_now
    from app.services.retention_service import _expired_conditions, _now as retention_now

    files = _scan(_dir())
    used = sum(files.values())
    _cache[str(_dir())] = (used, time.monotonic())
    level = _log_level_change(used)
    archive_files = _scan(Path(settings.ARCHIVE_DIR).resolve())

    def doc_rows(*conditions) -> list[tuple[str, int]]:
        q = select(Document.id, Document.file_size).where(*conditions).order_by(Document.uploaded_at, Document.id)
        return [(i, size or 0) for i, size in db.execute(q)]

    known = {Path(p).name for p in db.scalars(select(Document.file_path))}
    orphans = sorted((name, size) for name, size in files.items() if name not in known)
    overdue = doc_rows(*stale_overdue_conditions(cleanup_now()))
    overdue_ids = {i for i, _ in overdue}
    stale = [r for r in doc_rows(Document.status.in_(STALE_STATUSES), Document.stale_notified_at.is_not(None))
             if r[0] not in overdue_ids]

    return {
        "level": level,
        "reason": reason_of(used),
        "used_bytes": used,
        "limit_bytes": limit_bytes(),
        "used_percent": round(_percent(used), 1),
        "warn_percent": settings.STORAGE_WARN_PERCENT,
        "block_percent": settings.STORAGE_BLOCK_PERCENT,
        "file_count": len(files),
        "disk_total_bytes": disk_usage()[0],   # 업로드 폴더가 있는 디스크 전체 (참고)
        "disk_free_bytes": disk_usage()[1],    # 디스크 실제 남은 공간
        "min_free_bytes": min_free_bytes(),    # 이보다 적으면 한도와 상관없이 block
        "disk_low": _disk_low(),
        "archive_bytes": sum(archive_files.values()),   # 참고용. 사용률에는 넣지 않는다
        "archive_file_count": len(archive_files),
        "candidates": [
            _group("orphan_files", "auto_delete", orphans),
            _group("failed_documents", "auto_delete", doc_rows(Document.status == DocumentStatus.FAILED)),
            _group("stale_overdue_documents", "manual_delete", overdue),
            _group("stale_documents", "manual_delete", stale),
            _group("retention_expired_documents", "archive", doc_rows(*_expired_conditions(retention_now()))),
        ],
    }
