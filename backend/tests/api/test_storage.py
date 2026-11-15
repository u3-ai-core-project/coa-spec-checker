"""[담당: 홍채령] 저장 공간 80% 경고·95% 업로드 차단 테스트 (운영 정책 1장). 실제 DB 필요.

한도는 STORAGE_LIMIT_GB 를 아주 작게(바이트 단위) 바꿔 시험한다. 업로드 폴더만 세고 보관용 폴더는 세지 않는다.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.enums import DocumentStatus
from app.models import Document
from app.services import storage_service
from tests.api.test_document_delete import PDF, make_doc  # noqa: F401 (fixture)

GB = 1024 ** 3


@pytest.fixture(autouse=True)
def roomy_disk(monkeypatch):
    """이 파일에서는 안전장치를 기본값(2GB)으로 켜고, 디스크는 넉넉하다고 본다 (실제 디스크와 상관없게)."""
    monkeypatch.setattr(settings, "MIN_FREE_DISK_GB", 2)
    monkeypatch.setattr(storage_service, "disk_usage", lambda: (500 * GB, 400 * GB))


def disk_free(monkeypatch, free: int):
    monkeypatch.setattr(storage_service, "disk_usage", lambda: (500 * GB, free))


@pytest.fixture
def limit(monkeypatch):
    """limit(바이트) → 저장 공간 한도를 그 바이트로 바꾼다."""
    def _set(n: int):
        monkeypatch.setattr(settings, "STORAGE_LIMIT_GB", n / GB)
        storage_service.invalidate()
    return _set


def fill(n: int, name="filler.bin") -> Path:
    """업로드 폴더에 n 바이트 파일을 직접 만든다 (문서 없이 공간만 차지)."""
    upload = Path(settings.UPLOAD_DIR)
    upload.mkdir(parents=True, exist_ok=True)
    path = upload / name
    path.write_bytes(b"0" * n)
    storage_service.invalidate()
    return path


def status(client):
    r = client.get("/api/v1/storage")
    assert r.status_code == 200
    return r.json()["data"]


def upload(client):
    return client.post("/api/v1/documents", files={"file": ("doc.pdf", PDF)}, data={"material_code": "LI2CO3"})


@pytest.mark.parametrize("used, level", [(0, "ok"), (790, "ok"), (800, "warn"), (949, "warn"), (950, "block")])
def test_levels(auth_client, db, limit, used, level):
    limit(1000)
    if used:
        fill(used)
    data = status(auth_client)
    assert data["level"] == level
    assert data["reason"] == ("quota" if level == "block" else None)
    assert data["used_percent"] == round(used / 10, 1)
    assert data["warn_percent"] == 80 and data["block_percent"] == 95


def test_upload_rejected_when_blocked(auth_client, make_doc, db, limit):
    make_doc()  # 규격 세트 준비
    limit(1000)
    fill(960)
    r = upload(auth_client)
    assert r.status_code == 507 and r.json()["error"]["code"] == "STORAGE_FULL"
    assert db.query(Document).count() == 1


def test_upload_rejected_when_new_file_would_cross_block(auth_client, make_doc, db, limit):
    make_doc()
    used = sum(p.stat().st_size for p in Path(settings.UPLOAD_DIR).iterdir())
    limit(used + len(PDF) * 10)       # 지금은 ok
    fill(len(PDF) * 9 - 5, "a.bin")   # 남은 공간 < 새 파일 + 5% → 받으면 95% 를 넘는다
    assert status(auth_client)["level"] in ("ok", "warn")
    r = upload(auth_client)
    assert r.status_code == 507 and r.json()["error"]["code"] == "STORAGE_FULL"


def test_batch_rejected_as_a_whole(auth_client, make_doc, db, limit):
    make_doc()
    limit(1000)
    fill(900)
    r = auth_client.post("/api/v1/documents/batch", files=[("files", ("a.pdf", PDF, "application/pdf"))],
                         data={"material_code": "LI2CO3"})
    assert r.status_code == 507 and r.json()["error"]["code"] == "STORAGE_FULL"
    assert db.query(Document).count() == 1


def test_upload_ok_counts_new_file(auth_client, make_doc, db, limit):
    limit(10 * GB)
    assert upload(auth_client).status_code == 201
    first = storage_service.used_bytes()
    assert upload(auth_client).status_code == 201
    assert storage_service.used_bytes() == first + len(PDF)  # 기억한 값에 바로 더해진다


def test_viewing_and_review_still_work_when_blocked(auth_client, make_doc, db, limit):
    doc_id = make_doc()
    limit(1000)
    fill(990)
    assert status(auth_client)["level"] == "block"
    assert auth_client.get(f"/api/v1/documents/{doc_id}").status_code == 200
    assert auth_client.get(f"/api/v1/documents/{doc_id}/file").status_code == 200
    item = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"][0]["item_id"]
    assert auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{item}/confirm").status_code == 200
    assert auth_client.post(f"/api/v1/documents/{doc_id}/approve",
                            json={"decision": "accept", "reason": None}).status_code == 200


def test_archive_folder_not_counted_and_move_lowers_usage(auth_client, make_doc, admin, db, monkeypatch):
    doc_id = make_doc()
    auth_client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept", "reason": None})
    auth_client.login_as(admin)
    before = auth_client.get("/api/v1/admin/storage").json()["data"]
    assert before["used_bytes"] == len(PDF) and before["archive_bytes"] == 0

    doc = db.get(Document, doc_id)
    doc.retention_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert auth_client.post(f"/api/v1/documents/{doc_id}/archive").status_code == 200

    after = auth_client.get("/api/v1/admin/storage").json()["data"]
    assert after["used_bytes"] == 0 and after["archive_bytes"] == len(PDF)
    assert storage_service.used_bytes() == 0


def test_delete_lowers_usage(auth_client, make_doc, db):
    doc_id = make_doc()
    assert storage_service.used_bytes() == len(PDF)
    auth_client.request("DELETE", f"/api/v1/documents/{doc_id}", json={"reason": "잘못 올림"})
    assert storage_service.used_bytes() == 0


def test_candidates_in_priority_order(auth_client, make_doc, admin, db):
    failed, overdue, stale, expired = (make_doc() for _ in range(4))
    now = datetime.now(timezone.utc)
    docs = {i: db.get(Document, i) for i in (failed, overdue, stale, expired)}
    docs[failed].status = DocumentStatus.FAILED
    docs[overdue].stale_notified_at = now - timedelta(days=8)
    docs[stale].stale_notified_at = now - timedelta(days=1)
    docs[expired].status = DocumentStatus.APPROVED
    docs[expired].retention_until = now - timedelta(days=1)
    db.commit()
    fill(123, "orphan.pdf")

    auth_client.login_as(admin)
    data = auth_client.get("/api/v1/admin/storage").json()["data"]
    groups = [(g["kind"], g["action"], g["count"], g["ids"]) for g in data["candidates"]]
    assert groups == [
        ("orphan_files", "auto_delete", 1, ["orphan.pdf"]),
        ("failed_documents", "auto_delete", 1, [failed]),
        ("stale_overdue_documents", "manual_delete", 1, [overdue]),
        ("stale_documents", "manual_delete", 1, [stale]),
        ("retention_expired_documents", "archive", 1, [expired]),
    ]
    assert data["candidates"][0]["bytes"] == 123
    assert data["candidates"][1]["bytes"] == len(PDF)
    # 상세 조회는 아무것도 지우지 않는다
    db.expire_all()
    assert all(db.get(Document, i) is not None for i in (failed, overdue, stale, expired))
    assert (Path(settings.UPLOAD_DIR) / "orphan.pdf").exists()


def test_user_sees_level_but_not_detail(auth_client, db):
    assert status(auth_client)["level"] == "ok"
    r = auth_client.get("/api/v1/admin/storage")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_level_change_logged_once(auth_client, db, limit, caplog):
    import logging
    caplog.set_level(logging.WARNING, logger="app.services.storage_service")
    limit(1000)
    status(auth_client)
    fill(850)
    status(auth_client)
    status(auth_client)
    lines = [r.getMessage() for r in caplog.records if "단계" in r.getMessage()]
    assert len(lines) == 1 and "ok → warn" in lines[0] and "85.0%" in lines[0]


# ---- 안전장치: 디스크 실제 남은 공간 -----------------------------------------
def test_disk_low_blocks_regardless_of_limit(auth_client, make_doc, admin, db, limit, monkeypatch):
    make_doc()
    limit(100 * GB)  # 한도로는 0%
    disk_free(monkeypatch, int(1.5 * GB))  # 기본 안전 기준 2GB 보다 적다
    assert status(auth_client)["level"] == "block" and status(auth_client)["reason"] == "disk"
    r = upload(auth_client)
    assert r.status_code == 507 and r.json()["error"]["code"] == "STORAGE_FULL"
    assert "디스크" in r.json()["error"]["message"]
    auth_client.login_as(admin)
    detail = auth_client.get("/api/v1/admin/storage").json()["data"]
    assert detail["disk_low"] is True and detail["disk_free_bytes"] == int(1.5 * GB)
    assert detail["min_free_bytes"] == 2 * GB


def test_disk_low_counts_incoming_file(auth_client, make_doc, limit, monkeypatch):
    make_doc()
    limit(100 * GB)
    disk_free(monkeypatch, 2 * GB + len(PDF) - 1)  # 이 파일을 받으면 2GB 아래로 내려간다
    assert status(auth_client)["level"] == "ok"
    assert upload(auth_client).status_code == 507


def test_disk_check_can_be_turned_off(auth_client, make_doc, limit, monkeypatch):
    make_doc()
    limit(100 * GB)
    disk_free(monkeypatch, 10)
    monkeypatch.setattr(settings, "MIN_FREE_DISK_GB", 0)
    assert status(auth_client)["level"] == "ok"
    assert upload(auth_client).status_code == 201
