"""[담당: 홍채령] 저장 폴더·파일 권한 (운영 정책 3장: "저장 폴더는 비공개로 두고 실행 권한을 주지 않는다").

- 폴더(UPLOAD_DIR, ARCHIVE_DIR): 0o700 — 서버를 돌리는 계정만 들어가 읽고 쓸 수 있다
- 파일: 0o600 — 서버 계정만 읽고 쓸 수 있고, 누구에게도 실행 권한(x)이 없다
  (올린 파일이 실행 파일이어도 서버에서 바로 실행될 수 없게 한다)

폴더는 서버가 시작할 때 만들고 권한을 맞춘다 (main.py lifespan → ensure_storage_dirs). 이미 있던 파일 권한도 이때 고친다.
파일은 처음 만들 때부터 0o600 으로 만든다 (만든 뒤 권한을 바꾸면 그 사이에 다른 계정이 열 틈이 생긴다).

원본 파일은 정적 파일 경로(StaticFiles)로 공개하지 않는다. 볼 때는 로그인한 사용자만
GET /documents/{id}/file 로 받는다. 저장 이름은 문서 ID 라 원래 파일 이름을 추측해 접근할 수도 없다.

Windows 는 이런 권한 비트가 없어 chmod 가 일부만 적용된다. 실패해도 서버는 뜨고 경고만 남긴다.
"""
import logging
import os
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

DIR_MODE = 0o700
FILE_MODE = 0o600


def ensure_private_dir(path: Path | str) -> Path:
    """폴더가 없으면 만들고, 권한을 0o700 으로 맞춘다."""
    path = Path(path)
    path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    _chmod(path, DIR_MODE)
    return path


def write_private_file(path: Path, content: bytes) -> None:
    """새 파일을 0o600 으로 만들어 쓴다. 같은 이름 파일이 이미 있으면 덮어쓰지 않고 FileExistsError."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    _chmod(path, FILE_MODE)  # umask 가 더 넓게 열어 두는 일은 없지만, 확실히 맞춰 둔다


def make_private(path: Path) -> None:
    """이미 있는 파일 권한을 0o600 으로 (보관용 폴더로 옮긴 파일 등)."""
    _chmod(path, FILE_MODE)


def ensure_storage_dirs() -> None:
    """서버 시작 때 부른다. 업로드·보관용 폴더를 0o700 으로 만들고, 안에 있던 파일을 0o600 으로 고친다."""
    for folder in (settings.UPLOAD_DIR, settings.ARCHIVE_DIR):
        path = ensure_private_dir(folder)
        fixed = 0
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False) and (entry.stat(follow_symlinks=False).st_mode & 0o777) != FILE_MODE:
                _chmod(Path(entry.path), FILE_MODE)
                fixed += 1
        if fixed:
            logger.warning("저장 폴더 파일 %d개의 권한을 0o600 으로 고쳤습니다: %s", fixed, path)


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as e:
        logger.warning("권한을 바꾸지 못했습니다 (%s): %s", type(e).__name__, path)
