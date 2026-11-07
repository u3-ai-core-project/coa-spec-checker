"""[담당: 장수민] 문서 재처리 API (POST /documents/{id}/retry)와 서버 시작 시 멈춘 문서 정리 테스트. 실제 DB 필요.

재처리(실패 문서만, 권한, 중복 요청), 멈춘 문서 정리(대기·처리 중 → 실패), 서버 시작 시 자동 정리.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.enums import DocumentStatus, Role, SpecType
from app.main import app
from app.models import Document, SpecItem, SpecSet, User
from app.services import document_service

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100
GOOD = {"items": [{"raw_name": "Na", "normalized_name": "Na", "mapping_source": "dictionary",
                   "raw_value": "12", "unit": "ppm", "confidence": 0.95}]}
EMPTY = {"items": []}  # 시험 항목이 없으면 추출 실패


@pytest.fixture
def mock_dir(db, tmp_path, monkeypatch):
    """규격 세트(Na ≤ 50 ppm)를 만들고, 업로드 파일(doc.pdf)에 대응하는 목업 추출 JSON 폴더를 돌려준다."""
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    path = tmp_path / "mock"
    path.mkdir()
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(path))
    return path


def set_mock(mock_dir: Path, data: dict) -> None:
    (mock_dir / "doc.json").write_text(json.dumps(data), encoding="utf-8")


def upload(client) -> str:
    r = client.post("/api/v1/documents", files={"file": ("doc.pdf", PDF)}, data={"material_code": "LI2CO3"})
    assert r.status_code == 201
    return r.json()["data"]["document_id"]


def reload(db, doc_id: str) -> Document:
    db.expire_all()
    return db.get(Document, doc_id)


def set_status(db, doc_id: str, status: DocumentStatus, error_message: str | None = None) -> None:
    doc = db.get(Document, doc_id)
    doc.status = status
    doc.error_message = error_message
    db.commit()


def retry(client, doc_id: str):
    return client.post(f"/api/v1/documents/{doc_id}/retry")


@pytest.fixture
def failed_doc(auth_client, mock_dir, db) -> str:
    """추출에 실패한 문서. 이 문서를 올린 사람은 user 다."""
    set_mock(mock_dir, EMPTY)
    doc_id = upload(auth_client)
    assert reload(db, doc_id).status == DocumentStatus.FAILED
    return doc_id


# ---- 재처리 ----------------------------------------------------------------
def test_retry_failed_document_extracts_again(auth_client, mock_dir, failed_doc, db):
    set_mock(mock_dir, GOOD)  # 이번에는 추출이 된다

    r = retry(auth_client, failed_doc)

    assert r.status_code == 200
    assert r.json()["data"] == {"document_id": failed_doc, "file_name": "doc.pdf", "status": "queued"}
    # TestClient 는 응답 뒤 BackgroundTasks 를 바로 실행한다 → 이미 extracted
    doc = reload(db, failed_doc)
    assert doc.status == DocumentStatus.EXTRACTED
    assert doc.error_message is None
    assert doc.lot_recommendation is not None
    assert doc.extraction is not None and doc.extraction.result["items"]


def test_retry_can_fail_again(auth_client, failed_doc, db):
    """고치지 않고 다시 처리하면 또 failed. 다시 시도할 수 있다."""
    assert retry(auth_client, failed_doc).status_code == 200
    doc = reload(db, failed_doc)
    assert doc.status == DocumentStatus.FAILED and doc.error_message
    assert retry(auth_client, failed_doc).status_code == 200


def test_retry_queues_once(auth_client, failed_doc, db, monkeypatch):
    """응답은 queued 이고 추출은 한 번만 등록된다. 이어서 또 누르면 409."""
    started = []
    monkeypatch.setattr("app.api.v1.documents.process_document", lambda doc_id: started.append(doc_id))

    r = retry(auth_client, failed_doc)

    assert r.status_code == 200 and r.json()["data"]["status"] == "queued"
    doc = reload(db, failed_doc)
    assert doc.status == DocumentStatus.QUEUED and doc.error_message is None
    assert started == [failed_doc]

    again = retry(auth_client, failed_doc)
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_FAILED"
    assert started == [failed_doc]


@pytest.mark.parametrize("status", [
    DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.EXTRACTED,
    DocumentStatus.IN_REVIEW, DocumentStatus.ON_HOLD, DocumentStatus.APPROVED,
])
def test_retry_only_failed(auth_client, mock_dir, db, status):
    set_mock(mock_dir, GOOD)
    doc_id = upload(auth_client)
    set_status(db, doc_id, status)

    r = retry(auth_client, doc_id)

    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_FAILED"
    assert reload(db, doc_id).status == status


def test_retry_missing_file(auth_client, failed_doc, db):
    Path(reload(db, failed_doc).file_path).unlink()

    r = retry(auth_client, failed_doc)

    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
    assert reload(db, failed_doc).status == DocumentStatus.FAILED


def test_retry_unknown_document(auth_client):
    r = retry(auth_client, "no-such-document")
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# ---- 권한 ------------------------------------------------------------------
def test_retry_by_other_user_forbidden(auth_client, failed_doc, db):
    other = User(username="user2", password_hash="x", name="박다른", role=Role.USER)
    db.add(other)
    db.commit()
    auth_client.login_as(other)

    r = retry(auth_client, failed_doc)

    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert reload(db, failed_doc).status == DocumentStatus.FAILED


def test_retry_by_admin(auth_client, mock_dir, failed_doc, admin, db):
    set_mock(mock_dir, GOOD)
    auth_client.login_as(admin)

    assert retry(auth_client, failed_doc).status_code == 200
    assert reload(db, failed_doc).status == DocumentStatus.EXTRACTED


def test_retry_requires_login(client):
    assert client.post("/api/v1/documents/anything/retry").status_code == 401


# ---- 멈춘 문서 정리 ----------------------------------------------------------
def test_recover_stuck_documents(auth_client, mock_dir, db):
    set_mock(mock_dir, GOOD)
    ids = {s: upload(auth_client) for s in ("queued", "processing", "extracted", "approved", "failed")}
    set_status(db, ids["queued"], DocumentStatus.QUEUED)
    set_status(db, ids["processing"], DocumentStatus.PROCESSING)
    set_status(db, ids["approved"], DocumentStatus.APPROVED)
    set_status(db, ids["failed"], DocumentStatus.FAILED, "원래 오류")

    assert document_service.recover_stuck_documents(db) == 2

    for name in ("queued", "processing"):
        doc = reload(db, ids[name])
        assert doc.status == DocumentStatus.FAILED and doc.error_message == document_service.MSG_INTERRUPTED
    assert reload(db, ids["extracted"]).status == DocumentStatus.EXTRACTED
    assert reload(db, ids["approved"]).status == DocumentStatus.APPROVED
    failed = reload(db, ids["failed"])
    assert failed.status == DocumentStatus.FAILED and failed.error_message == "원래 오류"
    assert document_service.recover_stuck_documents(db) == 0  # 이미 정리됨


def test_stuck_document_can_be_retried_or_deleted_after_recovery(auth_client, mock_dir, db):
    """정리 전에는 다시 처리도 삭제도 못 하지만, 정리하면 둘 다 할 수 있다."""
    set_mock(mock_dir, GOOD)
    a, b = upload(auth_client), upload(auth_client)
    set_status(db, a, DocumentStatus.PROCESSING)
    set_status(db, b, DocumentStatus.PROCESSING)
    assert retry(auth_client, a).json()["error"]["code"] == "NOT_FAILED"
    assert auth_client.delete(f"/api/v1/documents/{b}").json()["error"]["code"] == "NOT_READY"

    assert document_service.recover_stuck_documents(db) == 2

    assert retry(auth_client, a).status_code == 200
    assert reload(db, a).status == DocumentStatus.EXTRACTED
    assert auth_client.delete(f"/api/v1/documents/{b}").status_code == 200


# ---- 서버 시작 ----------------------------------------------------------------
def test_startup_recovers_stuck_documents(auth_client, mock_dir, db):
    set_mock(mock_dir, GOOD)
    doc_id = upload(auth_client)
    set_status(db, doc_id, DocumentStatus.PROCESSING)

    with TestClient(app):  # with 로 열어야 서버 시작 단계(lifespan)가 실행된다
        pass

    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.FAILED and doc.error_message == document_service.MSG_INTERRUPTED


def test_startup_survives_recovery_error(monkeypatch):
    def broken(_db):
        raise RuntimeError("DB 연결 실패")
    monkeypatch.setattr(document_service, "recover_stuck_documents", broken)

    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
