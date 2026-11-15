"""[담당: 홍채령] 업로드 크기 제한 테스트 (운영 정책 빠른 보안 수정). 실제 DB 필요.

파일을 1MB 씩 나눠 읽다가 상한(MAX_UPLOAD_MB)을 넘으면 바로 INVALID_FILE 로 막는다.
일괄 접수는 파일 수와 전체 합계 상한도 본다.
"""
import asyncio

import pytest

from app.api.v1 import documents as documents_api
from app.core.config import settings
from app.core.errors import AppException
from app.models import Document
from seeds.seed_specs import seed_specs

MB = 1024 * 1024
PDF_HEAD = b"%PDF-1.7\n"


def pdf_of(size: int) -> bytes:
    return PDF_HEAD + b"0" * (size - len(PDF_HEAD))


@pytest.fixture
def specs(db):
    seed_specs(db)
    db.commit()


def error(r):
    return r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]


def test_single_upload_over_limit_rejected(auth_client, specs, db, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    r = auth_client.post("/api/v1/documents", files={"file": ("big.pdf", pdf_of(MB + 1))},
                         data={"material_code": "LI2CO3"})

    assert error(r) == (400, "INVALID_FILE", "1MB 이하 파일만 업로드할 수 있습니다")
    assert db.query(Document).count() == 0


def test_single_upload_at_limit_accepted(auth_client, specs, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    r = auth_client.post("/api/v1/documents", files={"file": ("ok.pdf", pdf_of(MB))},
                         data={"material_code": "LI2CO3"})
    assert r.status_code == 201


def batch_post(auth_client, files, receipts: bytes | None = None):
    upload = [("files", (name, content, "application/pdf")) for name, content in files]
    if receipts is not None:
        upload.append(("receipts", ("receipts.csv", receipts, "text/csv")))
    return auth_client.post("/api/v1/documents/batch", files=upload, data={"material_code": "LI2CO3"})


def test_batch_file_over_limit_rejected(auth_client, specs, db, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    r = batch_post(auth_client, [("a.pdf", pdf_of(100)), ("b.pdf", pdf_of(MB + 1))])

    assert error(r) == (400, "INVALID_FILE", "1MB 이하 파일만 업로드할 수 있습니다")
    assert db.query(Document).count() == 0


def test_batch_total_over_limit_rejected(auth_client, specs, db, monkeypatch):
    """파일 하나하나는 상한 안이어도 합계가 넘으면 막는다. (기본 설정에선 파일 수 검사가 먼저 걸려 합계 상한을 작게 바꿔 시험)"""
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    monkeypatch.setattr(documents_api, "_batch_total_limit", lambda: MB + MB // 2)  # 1.5MB
    r = batch_post(auth_client, [("a.pdf", pdf_of(MB)), ("b.pdf", pdf_of(MB))])

    status, code, message = error(r)
    assert (status, code) == (400, "INVALID_FILE")
    assert "합계" in message
    assert db.query(Document).count() == 0


def test_batch_too_many_files_rejected_before_reading(auth_client, specs, monkeypatch):
    monkeypatch.setattr(settings, "MAX_BATCH_FILES", 2)
    r = batch_post(auth_client, [(f"{i}.pdf", pdf_of(100)) for i in range(3)])
    assert error(r)[:2] == (400, "VALIDATION_ERROR")


def test_batch_receipts_csv_over_limit_rejected(auth_client, specs, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    csv = b"receipt_id,received_lot\n" + b"R,L\n" * (MB // 4 + 1)
    r = batch_post(auth_client, [("a.pdf", pdf_of(100))], receipts=csv)
    status, code, message = error(r)
    assert (status, code) == (400, "INVALID_FILE")
    assert message.startswith("입고 정보 CSV")


class _CountingFile:
    """read() 가 몇 번 불렸는지 세는 가짜 업로드 파일. 상한을 넘으면 더 읽지 않는지 확인한다."""

    def __init__(self, total: int):
        self.left = total
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        n = min(size, self.left)
        self.left -= n
        return b"0" * n


def test_read_limited_stops_early():
    f = _CountingFile(total=50 * MB)
    with pytest.raises(AppException):
        asyncio.run(documents_api._read_limited(f, 2 * MB, message="too big"))
    assert f.reads == 3  # 1MB, 2MB, 3MB 째에서 멈춘다 (50MB 를 다 읽지 않음)
