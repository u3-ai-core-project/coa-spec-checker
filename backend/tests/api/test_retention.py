"""[담당: 홍채령] 보관 기간·보관용 폴더 이동 테스트 (운영 정책 1장). 실제 DB 필요.

- 처분하면 retention_until = 처분 시각 + RETENTION_YEARS, 처분 취소하면 비우고, 재처분하면 다시 센다
- 설정을 바꿔도 이미 처분한 문서의 기간은 그대로다
- 처분 완료 문서는 보관 기간이 지나도 삭제하지 않는다 (409). 원본을 보관용 폴더로 옮기는 것만 ADMIN 이 한다
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import settings
from app.models import Document
from app.services import retention_service
from tests.api.test_document_delete import delete, make_doc  # noqa: F401 (fixture)

EXPIRED = "/api/v1/documents/retention-expired"


def approve(client, doc_id):
    r = client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept", "reason": None})
    assert r.status_code == 200, r.text


def cancel(client, doc_id):
    r = client.post(f"/api/v1/documents/{doc_id}/cancel-approval", json={"reason": "처분 오류"})
    assert r.status_code == 200, r.text


def years_between(start: datetime, end: datetime) -> int:
    return end.year - start.year


@pytest.fixture
def later(monkeypatch):
    """보관 기간 검사에 쓰는 '지금'을 원하는 만큼 미래로 옮긴다."""
    def _move(**kw):
        monkeypatch.setattr(retention_service, "_now", lambda: datetime.now(timezone.utc) + timedelta(**kw))
    return _move


def test_retention_set_on_approve_and_cleared_on_cancel(auth_client, make_doc, admin, db):
    doc_id = make_doc()
    approve(auth_client, doc_id)
    doc = db.get(Document, doc_id)
    assert years_between(doc.approved_at, doc.retention_until) == 3
    assert doc.retention_until.month == doc.approved_at.month and doc.retention_until.day == doc.approved_at.day

    detail = auth_client.get(f"/api/v1/documents/{doc_id}").json()["data"]
    assert detail["retention_until"] is not None and detail["archived_at"] is None
    listed = auth_client.get("/api/v1/documents").json()["data"]["items"][0]
    assert listed["retention_until"] == detail["retention_until"]

    auth_client.login_as(admin)
    cancel(auth_client, doc_id)
    db.expire_all()
    assert db.get(Document, doc_id).retention_until is None


def test_reapprove_counts_from_new_approval(auth_client, make_doc, admin, db):
    doc_id = make_doc()
    approve(auth_client, doc_id)
    # 처음 처분을 1년 전으로 돌려 둔다
    doc = db.get(Document, doc_id)
    doc.approved_at -= timedelta(days=365)
    doc.retention_until -= timedelta(days=365)
    db.commit()
    first = doc.retention_until

    auth_client.login_as(admin)
    cancel(auth_client, doc_id)
    approve(auth_client, doc_id)
    db.expire_all()
    doc = db.get(Document, doc_id)
    assert doc.retention_until > first + timedelta(days=360)
    assert years_between(doc.approved_at, doc.retention_until) == 3


def test_setting_change_applies_to_later_approvals_only(auth_client, make_doc, db, monkeypatch):
    old_id, new_id = make_doc(), make_doc()
    approve(auth_client, old_id)
    monkeypatch.setattr(settings, "RETENTION_YEARS", 10)
    approve(auth_client, new_id)
    db.expire_all()
    old, new = db.get(Document, old_id), db.get(Document, new_id)
    assert years_between(old.approved_at, old.retention_until) == 3
    assert years_between(new.approved_at, new.retention_until) == 10


def test_approved_delete_blocked_within_and_after_retention(auth_client, make_doc, admin, db):
    doc_id = make_doc()
    approve(auth_client, doc_id)
    auth_client.login_as(admin)
    r = delete(auth_client, doc_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_APPROVED"
    assert "보관 기간(" in r.json()["error"]["message"] and "까지) 동안" in r.json()["error"]["message"]

    doc = db.get(Document, doc_id)
    doc.retention_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    r = delete(auth_client, doc_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_APPROVED"
    assert "보관용 폴더로 옮기는 것만" in r.json()["error"]["message"]
    db.expire_all()
    assert db.get(Document, doc_id) is not None


def test_archive_refused_before_expiry(auth_client, make_doc, admin):
    doc_id = make_doc()
    approve(auth_client, doc_id)
    auth_client.login_as(admin)
    r = auth_client.post(f"/api/v1/documents/{doc_id}/archive")
    assert r.status_code == 409 and r.json()["error"]["code"] == "RETENTION_NOT_EXPIRED"
    assert "까지)이 지나야" in r.json()["error"]["message"]


def test_archive_refused_for_not_approved(auth_client, make_doc, admin):
    doc_id = make_doc()
    auth_client.login_as(admin)
    r = auth_client.post(f"/api/v1/documents/{doc_id}/archive")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_APPROVED"


def test_archive_and_expired_list_admin_only(auth_client, make_doc, later):
    doc_id = make_doc()
    approve(auth_client, doc_id)
    later(days=3 * 366 + 1)
    assert auth_client.post(f"/api/v1/documents/{doc_id}/archive").json()["error"]["code"] == "FORBIDDEN"
    assert auth_client.get(EXPIRED).json()["error"]["code"] == "FORBIDDEN"


def test_archive_moves_file_and_file_still_served(auth_client, make_doc, admin, db, later):
    keep_id, doc_id = make_doc(), make_doc()
    approve(auth_client, keep_id)
    approve(auth_client, doc_id)
    auth_client.login_as(admin)
    assert auth_client.get(EXPIRED).json()["data"]["total"] == 0

    later(days=3 * 366 + 1)
    listed = auth_client.get(EXPIRED).json()["data"]
    assert listed["total"] == 2

    src = Path(db.get(Document, doc_id).file_path)
    original = src.read_bytes()
    r = auth_client.post(f"/api/v1/documents/{doc_id}/archive")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["archived_at"] is not None

    db.expire_all()
    doc = db.get(Document, doc_id)
    dst = Path(doc.file_path)
    assert not src.exists()
    assert dst.parent == Path(settings.ARCHIVE_DIR) and dst.name == src.name
    assert dst.read_bytes() == original
    assert oct(dst.parent.stat().st_mode & 0o777) == oct(0o700)

    f = auth_client.get(f"/api/v1/documents/{doc_id}/file")
    assert f.status_code == 200 and f.content == original

    # 옮긴 문서는 목록에서 빠지고, 다시 옮길 수 없다
    assert [i["document_id"] for i in auth_client.get(EXPIRED).json()["data"]["items"]] == [keep_id]
    r = auth_client.post(f"/api/v1/documents/{doc_id}/archive")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_ARCHIVED"
    # 옮긴 뒤에도 삭제는 안 된다
    assert delete(auth_client, doc_id).status_code == 409


def test_archive_missing_document(auth_client, admin):
    auth_client.login_as(admin)
    r = auth_client.post("/api/v1/documents/00000000-0000-0000-0000-000000000000/archive")
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
