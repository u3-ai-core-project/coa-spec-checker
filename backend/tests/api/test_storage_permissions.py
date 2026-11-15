"""[담당: 홍채령] 저장 폴더·파일 권한 테스트 (운영 정책 3장, app/core/private_files.py). 실제 DB 필요 (업로드 테스트).

폴더 0o700, 파일 0o600 (실행 권한 없음). Windows 는 권한 비트가 없어 건너뛴다.
"""
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core import private_files
from app.core.config import settings
from app.core.enums import DocumentStatus
from app.main import app
from app.models import Document
from seeds.seed_specs import seed_specs

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Windows 는 POSIX 권한 비트가 없다")

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


def mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_startup_creates_private_dirs_and_fixes_existing_files(tmp_path, monkeypatch):
    uploads, archive = tmp_path / "up", tmp_path / "ar"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(settings, "ARCHIVE_DIR", str(archive))
    uploads.mkdir(mode=0o755)
    loose = uploads / "old.pdf"
    loose.write_bytes(b"x")
    os.chmod(loose, 0o755)  # 예전에 실행 권한까지 열린 채 저장된 파일
    os.chmod(uploads, 0o755)

    private_files.ensure_storage_dirs()

    assert mode(uploads) == 0o700 and mode(archive) == 0o700
    assert mode(loose) == 0o600


def test_server_startup_runs_permission_fix(tmp_path, monkeypatch):
    """앱 lifespan(서버 시작)에서 실제로 부른다."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "up"))
    monkeypatch.setattr(settings, "ARCHIVE_DIR", str(tmp_path / "ar"))
    from fastapi.testclient import TestClient
    with TestClient(app):
        pass
    assert mode(tmp_path / "up") == 0o700 and mode(tmp_path / "ar") == 0o700


def test_write_private_file_never_overwrites(tmp_path):
    path = tmp_path / "a.pdf"
    private_files.write_private_file(path, b"1")
    assert mode(path) == 0o600
    with pytest.raises(FileExistsError):
        private_files.write_private_file(path, b"2")
    assert path.read_bytes() == b"1"


def test_uploaded_file_is_private(auth_client, db):
    seed_specs(db)
    db.commit()
    r = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)}, data={"material_code": "LI2CO3"})
    assert r.status_code == 201
    doc = db.get(Document, r.json()["data"]["document_id"])
    assert mode(doc.file_path) == 0o600
    assert mode(settings.UPLOAD_DIR) == 0o700
    assert Path(doc.file_path).name.startswith(doc.id)  # 저장 이름은 문서 ID


def test_archived_file_is_private(auth_client, db, admin):
    seed_specs(db)
    db.commit()
    r = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)}, data={"material_code": "LI2CO3"})
    doc = db.get(Document, r.json()["data"]["document_id"])
    os.chmod(doc.file_path, 0o644)  # 옮기기 전 권한이 넓어져 있어도
    doc.status = DocumentStatus.APPROVED
    doc.retention_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    auth_client.login_as(admin)
    r = auth_client.post(f"/api/v1/documents/{doc.id}/archive")
    assert r.status_code == 200, r.text
    db.refresh(doc)
    assert Path(doc.file_path).parent == Path(settings.ARCHIVE_DIR)
    assert mode(doc.file_path) == 0o600 and mode(settings.ARCHIVE_DIR) == 0o700


def test_no_static_mount_exposes_storage():
    """저장 폴더를 정적 파일 경로로 내보내지 않는다. 원본은 로그인 후 GET /documents/{id}/file 로만."""
    from starlette.routing import Mount
    assert not [r for r in app.routes if isinstance(r, Mount)]
