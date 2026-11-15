"""[담당: 홍채령] 문서 삭제 API 테스트 (DELETE /documents/{id}). 실제 DB 필요.

삭제 결과(목록·상세·원본 파일·이력), 권한(본인·ADMIN·다른 USER), 처분 완료·추출 중 문서 차단, 삭제 사유 필수.
삭제 기록(deletion_logs) 내용은 tests/api/test_deletion_logs.py 에서 본다.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.enums import DocumentStatus, Role, SpecType
from app.models import ApprovalLog, DeletionLog, Document, ExtractionResult, ReviewLog, SpecItem, SpecSet, User

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


@pytest.fixture
def make_doc(auth_client, db, tmp_path, monkeypatch):
    """승인 권고가 나오는 목업 문서를 user 로 올린다. 규격: Na ≤ 50 ppm."""
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "doc.json").write_text(json.dumps({"items": [
        {"raw_name": "Na", "normalized_name": "Na", "mapping_source": "dictionary",
         "raw_value": "12", "unit": "ppm", "confidence": 0.95},
    ]}), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _make() -> str:
        r = auth_client.post("/api/v1/documents", files={"file": ("doc.pdf", PDF)}, data={"material_code": "LI2CO3"})
        assert r.status_code == 201
        return r.json()["data"]["document_id"]
    return _make


def delete(client, doc_id, reason="잘못 올린 문서"):
    body = {"reason": reason} if reason is not None else None
    return client.request("DELETE", f"/api/v1/documents/{doc_id}", json=body)


def count(db, model, doc_id):
    return db.scalar(select(func.count()).select_from(model).where(model.document_id == doc_id))


def test_delete_own_document(auth_client, make_doc, db):
    doc_id = make_doc()
    path = Path(db.get(Document, doc_id).file_path)
    assert path.is_file()

    r = delete(auth_client, doc_id)

    assert r.status_code == 200
    assert r.json()["data"] == {"document_id": doc_id}
    db.expire_all()
    assert db.get(Document, doc_id) is None
    assert not path.exists()
    assert auth_client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert auth_client.get("/api/v1/documents").json()["data"]["total"] == 0


def test_delete_removes_extraction_and_review_logs(auth_client, make_doc, db):
    """처분 기록이 없으면 추출 결과, 검수 이력이 함께 지워진다."""
    doc_id = make_doc()
    items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    assert auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{items[0]['item_id']}/confirm").status_code == 200
    assert count(db, ExtractionResult, doc_id) == 1
    assert count(db, ReviewLog, doc_id) == 1

    assert delete(auth_client, doc_id).status_code == 200

    db.expire_all()
    assert count(db, ExtractionResult, doc_id) == 0
    assert count(db, ReviewLog, doc_id) == 0


def test_held_document_can_be_deleted(auth_client, make_doc, db):
    """보류 이력이 있어도 지울 수 있다. 이력 요약은 삭제 기록에 남는다."""
    doc_id = make_doc()
    assert auth_client.post(f"/api/v1/documents/{doc_id}/hold",
                            json={"follow_up": "request_detection_limit", "reason": "검출한계 요청"}).status_code == 200

    assert delete(auth_client, doc_id).status_code == 200
    db.expire_all()
    assert count(db, ApprovalLog, doc_id) == 0
    assert count(db, DeletionLog, doc_id) == 1


@pytest.mark.parametrize("reason", [None, "", "   ", "x", "가" * 501])
def test_reason_required(auth_client, make_doc, db, reason):
    doc_id = make_doc()
    r = delete(auth_client, doc_id, reason=reason)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "REASON_REQUIRED"
    db.expire_all()
    assert db.get(Document, doc_id) is not None
    assert count(db, DeletionLog, doc_id) == 0


def test_admin_can_delete_others_document(auth_client, make_doc, admin):
    doc_id = make_doc()
    auth_client.login_as(admin)
    assert delete(auth_client, doc_id).status_code == 200


def test_other_user_cannot_delete(auth_client, make_doc, db):
    doc_id = make_doc()
    other = User(username="user2", password_hash="x", name="박다른", role=Role.USER)
    db.add(other)
    db.commit()
    auth_client.login_as(other)

    r = delete(auth_client, doc_id)

    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    db.expire_all()
    assert db.get(Document, doc_id) is not None


def test_approved_document_cannot_be_deleted(auth_client, make_doc, admin, db):
    """처분 완료 문서는 지울 수 없다. ADMIN 이 처분 취소하면 지울 수 있고, 처분 이력 요약이 삭제 기록에 남는다."""
    doc_id = make_doc()
    auth_client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept", "reason": None})

    auth_client.login_as(admin)
    r = delete(auth_client, doc_id)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ALREADY_APPROVED"

    assert auth_client.post(f"/api/v1/documents/{doc_id}/cancel-approval",
                            json={"reason": "삭제하려고 취소"}).status_code == 200
    assert delete(auth_client, doc_id).status_code == 200
    db.expire_all()
    assert db.get(Document, doc_id) is None
    log = db.scalar(select(DeletionLog).where(DeletionLog.document_id == doc_id))
    assert [a["action"] for a in log.approval_summary] == ["approve", "cancel"]  # 승인 + 취소 기록이 요약으로 남는다


def test_processing_document_cannot_be_deleted(auth_client, make_doc, db):
    doc_id = make_doc()
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.PROCESSING
    db.commit()

    r = delete(auth_client, doc_id)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_delete_missing_document(auth_client):
    r = delete(auth_client, "00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_delete_requires_login(client):
    assert client.delete("/api/v1/documents/anything").status_code == 401
