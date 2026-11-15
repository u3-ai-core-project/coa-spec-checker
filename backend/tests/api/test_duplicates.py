"""[담당: 홍채령] 같은 파일 다시 올리기 경고 + 일괄 접수 묶음 삭제 테스트 (운영 정책 1장). 실제 DB 필요."""
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import DocumentStatus
from app.models import Batch, DeletionLog, Document, Receipt
from tests.api.test_document_delete import PDF, make_doc  # noqa: F401 (fixture)

OTHER = PDF + b"\n%other"


@pytest.fixture(autouse=True)
def check_on(monkeypatch):
    monkeypatch.setattr(settings, "DUPLICATE_FILE_CHECK", True)


def upload(client, content=PDF, name="doc.pdf", **data):
    return client.post("/api/v1/documents", files={"file": (name, content)},
                       data={"material_code": "LI2CO3", **data})


def batch(client, files, **data):
    return client.post("/api/v1/documents/batch",
                       files=[("files", (n, c, "application/pdf")) for n, c in files],
                       data={"material_code": "LI2CO3", **data})


# ---- A. 같은 파일 경고 -------------------------------------------------------
def test_duplicate_blocked_then_confirmed(auth_client, make_doc, db, user):
    first = make_doc()  # 같은 PDF 로 첫 문서
    r = upload(auth_client, name="again.pdf")
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "DUPLICATE_FILE" and "doc.pdf" in body["error"]["message"]
    [dup] = body["data"]["duplicates"]
    assert dup["document_id"] == first and dup["file_name"] == "doc.pdf" and dup["uploaded_by"] == user.id
    assert dup["status"] and dup["uploaded_at"] and dup["archived"] is False
    assert db.query(Document).count() == 1  # 아무것도 저장 안 됨

    r = upload(auth_client, name="again.pdf", confirm_duplicate="true")
    assert r.status_code == 201
    new_id = r.json()["data"]["document_id"]
    detail = auth_client.get(f"/api/v1/documents/{new_id}").json()["data"]
    assert detail["duplicate_of"] == first and len(detail["file_sha256"]) == 64
    assert db.query(Document).count() == 2  # 기존 문서는 그대로 (자동 삭제 없음)


def test_different_file_not_duplicate(auth_client, make_doc, db):
    make_doc()
    r = upload(auth_client, OTHER, name="doc.pdf")  # 이름이 같아도 내용이 다르면 통과
    assert r.status_code == 201
    assert auth_client.get(f"/api/v1/documents/{r.json()['data']['document_id']}").json()["data"]["duplicate_of"] is None


def test_duplicate_of_failed_or_archived_doc_also_warned(auth_client, make_doc, db):
    doc = db.get(Document, make_doc())
    doc.status = DocumentStatus.FAILED
    db.commit()
    r = upload(auth_client)
    assert r.status_code == 409 and r.json()["data"]["duplicates"][0]["status"] == "failed"


def test_deleted_doc_not_counted(auth_client, make_doc, db):
    doc_id = make_doc()
    auth_client.request("DELETE", f"/api/v1/documents/{doc_id}", json={"reason": "잘못 올림"})
    assert upload(auth_client).status_code == 201


def test_batch_duplicates_reported_per_file(auth_client, make_doc, db):
    first = make_doc()
    r = batch(auth_client, [("same.pdf", PDF), ("new.pdf", OTHER)])
    assert r.status_code == 201
    data = r.json()["data"]
    assert [d["file_name"] for d in data["documents"]] == ["new.pdf"]
    [rej] = data["rejected"]
    assert rej["file_name"] == "same.pdf" and rej["code"] == "DUPLICATE_FILE"
    assert rej["duplicates"][0]["document_id"] == first


def test_batch_same_file_twice_in_one_request(auth_client, make_doc, db):
    make_doc()  # 규격 세트 준비용. 파일은 OTHER 로 올린다
    r = batch(auth_client, [("a.pdf", OTHER), ("b.pdf", OTHER)])
    data = r.json()["data"]
    assert [d["file_name"] for d in data["documents"]] == ["a.pdf"]
    assert data["rejected"][0]["code"] == "DUPLICATE_FILE"


def test_batch_confirm_duplicate(auth_client, make_doc, db):
    first = make_doc()
    r = batch(auth_client, [("same.pdf", PDF)], confirm_duplicate="true")
    data = r.json()["data"]
    assert data["rejected"] == [] and len(data["documents"]) == 1
    assert db.get(Document, data["documents"][0]["document_id"]).duplicate_of == first


def test_check_can_be_turned_off(auth_client, make_doc, monkeypatch):
    make_doc()
    monkeypatch.setattr(settings, "DUPLICATE_FILE_CHECK", False)
    assert upload(auth_client).status_code == 201


# ---- B. 묶음 삭제 ------------------------------------------------------------
CSV = "receipt_id,received_lot\nR1,LOT-1\nR2,LOT-2\n"


def make_batch(client, files):
    upload = [("files", (n, c, "application/pdf")) for n, c in files]
    upload.append(("receipts", ("r.csv", CSV.encode(), "text/csv")))
    r = client.post("/api/v1/documents/batch", files=upload, data={"material_code": "LI2CO3"})
    assert r.status_code == 201, r.text
    return r.json()["data"]["batch_id"], [d["document_id"] for d in r.json()["data"]["documents"]]


def delete_batch(client, batch_id, reason="잘못 올린 묶음"):
    return client.request("DELETE", f"/api/v1/documents/batch/{batch_id}",
                          json={"reason": reason} if reason is not None else None)


def test_admin_deletes_batch_with_logs(auth_client, make_doc, admin, db):
    make_doc()
    batch_id, ids = make_batch(auth_client, [("a.pdf", OTHER), ("b.pdf", OTHER + b"b")])
    keep_id, keep_docs = make_batch(auth_client, [("c.pdf", OTHER + b"c")])
    files = [db.get(Document, i).file_path for i in ids]

    auth_client.login_as(admin)
    r = delete_batch(auth_client, batch_id)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"batch_id": batch_id, "deleted_documents": ids, "deleted_receipts": 2}

    db.expire_all()
    assert db.get(Batch, batch_id) is None
    assert db.scalar(select(Receipt).where(Receipt.batch_id == batch_id)) is None
    assert all(db.get(Document, i) is None for i in ids)
    from pathlib import Path
    assert not any(Path(f).exists() for f in files)
    logs = list(db.scalars(select(DeletionLog).where(DeletionLog.batch_id == batch_id).order_by(DeletionLog.id)))
    assert [(l.document_id, l.rule.value) for l in logs] == [(ids[0], "batch_delete"), (ids[1], "batch_delete"),
                                                              (None, "batch_delete")]
    assert logs[-1].review_summary["batch"] == {"documents": 2, "receipts": 2, "document_ids": ids}
    assert all(l.deleted_by == admin.id and l.reason == "잘못 올린 묶음" for l in logs)
    # 다른 묶음은 그대로
    assert db.get(Batch, keep_id) is not None and db.get(Document, keep_docs[0]) is not None


def test_user_cannot_delete_batch(auth_client, make_doc):
    make_doc()
    batch_id, _ = make_batch(auth_client, [("a.pdf", OTHER)])
    r = delete_batch(auth_client, batch_id)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("status", [DocumentStatus.APPROVED, DocumentStatus.PROCESSING])
def test_locked_document_blocks_batch_delete(auth_client, make_doc, admin, db, status):
    make_doc()
    batch_id, ids = make_batch(auth_client, [("a.pdf", OTHER), ("b.pdf", OTHER + b"b")])
    db.get(Document, ids[1]).status = status
    db.commit()
    auth_client.login_as(admin)
    r = delete_batch(auth_client, batch_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "BATCH_NOT_DELETABLE"
    assert r.json()["data"]["blocking"] == [{"document_id": ids[1], "file_name": "b.pdf", "status": status.value}]
    db.expire_all()
    assert db.get(Batch, batch_id) is not None and all(db.get(Document, i) is not None for i in ids)
    assert db.scalar(select(DeletionLog)) is None


@pytest.mark.parametrize("reason", [None, "", "x"])
def test_batch_delete_reason_required(auth_client, make_doc, admin, db, reason):
    make_doc()
    batch_id, _ = make_batch(auth_client, [("a.pdf", OTHER)])
    auth_client.login_as(admin)
    r = delete_batch(auth_client, batch_id, reason=reason)
    assert r.status_code == 400 and r.json()["error"]["code"] == "REASON_REQUIRED"
    db.expire_all()
    assert db.get(Batch, batch_id) is not None


def test_batch_delete_missing(auth_client, admin):
    auth_client.login_as(admin)
    assert delete_batch(auth_client, "nope").status_code == 404
