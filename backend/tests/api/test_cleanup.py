"""[담당: 홍채령] 자동 정리·방치 문서 테스트 (운영 정책 1장). 실제 DB 필요.

시간은 cleanup_service._now 를 미래로 옮겨 조절한다. 연결 안 된 파일의 나이는 파일 수정 시각(mtime)으로 정한다.
"""
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.enums import DocumentStatus
from app.models import DeletionLog, Document
from app.services import cleanup_service
from tests.api.test_document_delete import make_doc  # noqa: F401 (fixture)

RUN = "/api/v1/admin/cleanup/run"


@pytest.fixture
def at(monkeypatch):
    """at(days=..) → 정리 작업이 보는 '지금'을 실제 시각 + 그만큼으로 옮긴다."""
    def _move(**kw):
        monkeypatch.setattr(cleanup_service, "_now", lambda: datetime.now(timezone.utc) + timedelta(**kw))
    return _move


def run(db, dry_run=False):
    return cleanup_service.run_cleanup(db, dry_run=dry_run)


def make_failed(make_doc, db, days_ago: float) -> str:
    doc_id = make_doc()
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.FAILED
    doc.processing_finished_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.commit()
    return doc_id


def orphan(name: str, hours_ago: float) -> Path:
    upload = Path(settings.UPLOAD_DIR)
    upload.mkdir(parents=True, exist_ok=True)
    path = upload / name
    path.write_bytes(b"%PDF-1.7 orphan")
    old = time.time() - hours_ago * 3600
    os.utime(path, (old, old))
    return path


def logs(db, rule=None):
    q = select(DeletionLog)
    if rule:
        q = q.where(DeletionLog.rule == rule)
    return list(db.scalars(q))


# ---- (a) 실패 7일 ------------------------------------------------------------
def test_failed_older_than_7_days_deleted_with_log(auth_client, make_doc, db):
    old = make_failed(make_doc, db, days_ago=7.1)
    recent = make_failed(make_doc, db, days_ago=6)
    old_file = Path(db.get(Document, old).file_path)

    result = run(db)

    assert result.failed_documents_deleted == [old]
    db.expire_all()
    assert db.get(Document, old) is None and not old_file.exists()
    assert db.get(Document, recent) is not None
    [log] = logs(db, "auto_failed_7d")
    assert log.document_id == old and log.deleted_by is None and log.status_at_delete == "failed"
    assert "7일" in log.reason


def test_failed_without_finish_time_uses_upload_time(auth_client, make_doc, db, at):
    doc_id = make_failed(make_doc, db, days_ago=0)
    doc = db.get(Document, doc_id)
    doc.processing_finished_at = None
    db.commit()
    assert run(db).failed_documents_deleted == []
    at(days=8)
    assert run(db).failed_documents_deleted == [doc_id]


# ---- (b) 연결 안 된 파일 ------------------------------------------------------
def test_orphan_files(auth_client, make_doc, db):
    doc_id = make_doc()
    referenced = Path(db.get(Document, doc_id).file_path)
    os.utime(referenced, (time.time() - 48 * 3600,) * 2)  # 연결된 파일은 오래돼도 남는다
    old = orphan("old.pdf", hours_ago=25)
    new = orphan("new.pdf", hours_ago=23)
    hidden = orphan(".gitkeep", hours_ago=100)
    archive = Path(settings.ARCHIVE_DIR)
    archive.mkdir(parents=True, exist_ok=True)
    archived = archive / "x.pdf"
    archived.write_bytes(b"keep")
    os.utime(archived, (time.time() - 100 * 3600,) * 2)

    result = run(db)

    assert result.orphan_files_deleted == ["old.pdf"]
    assert not old.exists() and new.exists() and referenced.exists() and hidden.exists() and archived.exists()
    [log] = logs(db, "auto_orphan_file")
    assert log.document_id is None and log.file_name == "old.pdf" and log.file_size == len(b"%PDF-1.7 orphan")
    assert len(log.file_sha256) == 64 and log.deleted_by is None


def test_dry_run_changes_nothing(auth_client, make_doc, db, at):
    failed = make_failed(make_doc, db, days_ago=10)
    stale = make_doc()
    old = orphan("old.pdf", hours_ago=30)
    at(days=31)

    result = run(db, dry_run=True)

    assert result.dry_run is True
    assert result.failed_documents_deleted == [failed]
    assert result.orphan_files_deleted == ["old.pdf"]
    assert result.stale_documents_marked == [stale]
    db.expire_all()
    assert db.get(Document, failed) is not None and old.exists()
    assert db.get(Document, stale).stale_notified_at is None
    assert db.scalar(select(func.count()).select_from(DeletionLog)) == 0


def test_run_twice_is_safe(auth_client, make_doc, db, at):
    make_failed(make_doc, db, days_ago=10)
    make_doc()
    orphan("old.pdf", hours_ago=30)
    at(days=31)
    first = run(db)
    second = run(db)
    assert len(first.failed_documents_deleted) == 1 and len(first.orphan_files_deleted) == 1
    assert len(first.stale_documents_marked) == 1
    assert second.failed_documents_deleted == second.orphan_files_deleted == second.stale_documents_marked == []
    assert db.scalar(select(func.count()).select_from(DeletionLog)) == 2


def test_nothing_else_deleted(auth_client, make_doc, db, at):
    """처분 전 문서는 아무리 오래돼도 자동으로 지우지 않는다 (방치 표시만)."""
    doc_id = make_doc()
    at(days=400)
    result = run(db)
    assert result.failed_documents_deleted == [] and result.stale_documents_marked == [doc_id]
    db.expire_all()
    assert db.get(Document, doc_id) is not None


# ---- (c) 방치 ----------------------------------------------------------------
def test_stale_marked_after_30_days(auth_client, make_doc, db, at):
    doc_id = make_doc()
    at(days=29)
    assert run(db).stale_documents_marked == []
    at(days=31)
    assert run(db).stale_documents_marked == [doc_id]

    detail = auth_client.get(f"/api/v1/documents/{doc_id}").json()["data"]
    assert detail["is_stale"] is True and detail["stale_notified_at"] is not None
    # 올린 사람이 자기 방치 문서를 본다 (stale=true + uploaded_by=본인)
    uploader = db.get(Document, doc_id).uploaded_by
    stale_list = auth_client.get("/api/v1/documents", params={"stale": "true", "uploaded_by": uploader}).json()["data"]
    assert [i["document_id"] for i in stale_list["items"]] == [doc_id]
    assert auth_client.get("/api/v1/documents", params={"stale": "false"}).json()["data"]["total"] == 0


def test_stale_ignores_failed_processing_and_approved(auth_client, make_doc, db, at):
    ids = [make_doc() for _ in range(3)]
    for doc_id, status in zip(ids, (DocumentStatus.PROCESSING, DocumentStatus.QUEUED, DocumentStatus.APPROVED)):
        db.get(Document, doc_id).status = status
    db.commit()
    at(days=31)
    assert run(db).stale_documents_marked == []


def test_activity_resets_but_viewing_does_not(auth_client, make_doc, db, at):
    doc_id = make_doc()
    at(days=31)
    run(db)
    db.expire_all()
    assert db.get(Document, doc_id).stale_notified_at is not None
    before = db.get(Document, doc_id).last_activity_at

    # 조회는 활동이 아니다
    auth_client.get(f"/api/v1/documents/{doc_id}")
    auth_client.get(f"/api/v1/documents/{doc_id}/extraction")
    auth_client.get(f"/api/v1/documents/{doc_id}/file")
    db.expire_all()
    doc = db.get(Document, doc_id)
    assert doc.stale_notified_at is not None and doc.last_activity_at == before

    # 항목 확인은 활동이다 → 방치 표시가 풀리고 기간을 다시 센다
    item = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"][0]["item_id"]
    assert auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{item}/confirm").status_code == 200
    db.expire_all()
    doc = db.get(Document, doc_id)
    assert doc.stale_notified_at is None and doc.last_activity_at > before


@pytest.mark.parametrize("action", ["edit", "hold"])
def test_edit_and_hold_count_as_activity(auth_client, make_doc, db, action):
    doc_id = make_doc()
    doc = db.get(Document, doc_id)
    doc.stale_notified_at = datetime.now(timezone.utc)
    doc.last_activity_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()
    if action == "edit":
        item = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"][0]["item_id"]
        r = auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{item}",
                              json={"converted_value": 10, "reason": "값 수정"})
    else:
        r = auth_client.post(f"/api/v1/documents/{doc_id}/hold",
                             json={"follow_up": "request_detection_limit", "reason": "검출한계 요청"})
    assert r.status_code == 200, r.text
    db.expire_all()
    doc = db.get(Document, doc_id)
    assert doc.stale_notified_at is None
    assert doc.last_activity_at > datetime.now(timezone.utc) - timedelta(minutes=5)


def test_admin_overdue_list_after_grace(auth_client, make_doc, admin, db, monkeypatch):
    doc_id = make_doc()
    auth_client.login_as(admin)
    doc = db.get(Document, doc_id)
    doc.stale_notified_at = datetime.now(timezone.utc) - timedelta(days=6)
    db.commit()
    assert auth_client.get("/api/v1/documents/stale-overdue").json()["data"]["total"] == 0

    doc.stale_notified_at = datetime.now(timezone.utc) - timedelta(days=7, minutes=1)
    db.commit()
    data = auth_client.get("/api/v1/documents/stale-overdue").json()["data"]
    assert data["total"] == 1 and data["items"][0]["document_id"] == doc_id and data["items"][0]["is_stale"] is True


# ---- 관리자 실행 API ---------------------------------------------------------
def test_run_api_admin_only(auth_client, admin, make_doc, db):
    r = auth_client.post(RUN)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert auth_client.get("/api/v1/documents/stale-overdue").json()["error"]["code"] == "FORBIDDEN"

    failed = make_failed(make_doc, db, days_ago=10)
    auth_client.login_as(admin)
    r = auth_client.post(RUN, params={"dry_run": "true"})
    assert r.status_code == 200
    assert r.json()["data"] == {"dry_run": True, "failed_documents_deleted": [failed],
                                "orphan_files_deleted": [], "stale_documents_marked": []}
    db.expire_all()
    assert db.get(Document, failed) is not None
    r = auth_client.post(RUN)
    assert r.json()["data"]["failed_documents_deleted"] == [failed]
    db.expire_all()
    assert db.get(Document, failed) is None
