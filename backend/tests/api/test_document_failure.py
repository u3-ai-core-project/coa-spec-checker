"""[담당: 장수민] 처리 실패·재시도·복구 테스트 (운영 정책 4장). 실제 DB 필요.

시간 제한, 시도 기록(횟수·단계·종류), 일시 오류 자동 재시도, 처리 시작 선점, 멈춘 문서 정리·재시작.
"""
import time

from app.core.config import settings
from app.core.enums import DocumentStatus, ErrorKind
from app.models import Document
from app.pipeline import worker
from app.pipeline.extractor import ExtractionError
from app.services import document_service

# 같은 픽스처와 도우미를 쓴다
from tests.api.test_document_retry import (  # noqa: F401
    EMPTY, GOOD, PDF, mock_dir, reload, retry, set_mock, set_status, upload,
)


class FakeExtractor:
    """호출할 때마다 steps 의 다음 동작을 한다. 예외면 던지고, 숫자면 그만큼 자고, 그 외에는 값을 돌려준다."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = 0

    def extract(self, file_path, *, material_code, original_name=None):
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        if isinstance(step, Exception):
            raise step
        if isinstance(step, (int, float)):
            time.sleep(step)
            raise ExtractionError("늦게 끝남")
        return step


def good_extraction():
    from app.schemas.extraction import ExtractionInput
    return ExtractionInput.model_validate({**GOOD, "lot_no": "L1"})


def install(monkeypatch, steps) -> FakeExtractor:
    fake = FakeExtractor(steps)
    monkeypatch.setattr(worker, "get_extractor", lambda: fake)
    return fake


def queue_doc(auth_client, mock_dir, db, monkeypatch, steps):
    """추출기를 가짜로 바꾸고 문서를 올린다. 업로드가 끝나면 이미 처리가 끝나 있다 (TestClient)."""
    fake = install(monkeypatch, steps)
    doc_id = upload(auth_client)
    return doc_id, fake


# ---- 시도 기록 ---------------------------------------------------------------
def test_success_records_attempt_and_times(auth_client, mock_dir, db, monkeypatch):
    doc_id, fake = queue_doc(auth_client, mock_dir, db, monkeypatch, [good_extraction()])
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.EXTRACTED
    assert doc.attempt_count == 1 and fake.calls == 1
    assert doc.failed_stage is None and doc.error_kind is None
    assert doc.processing_started_at and doc.processing_finished_at >= doc.processing_started_at


def test_permanent_error_is_not_retried(auth_client, mock_dir, db, monkeypatch):
    doc_id, fake = queue_doc(auth_client, mock_dir, db, monkeypatch, [ExtractionError("손상된 파일")])
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.FAILED
    assert (doc.attempt_count, doc.failed_stage, doc.error_kind) == (1, "extract", ErrorKind.PERMANENT)
    assert doc.error_message == "손상된 파일" and fake.calls == 1


def test_empty_extraction_is_permanent(auth_client, mock_dir, db):
    set_mock(mock_dir, EMPTY)
    doc = reload(db, upload(auth_client))
    assert doc.status == DocumentStatus.FAILED
    assert (doc.failed_stage, doc.error_kind) == ("extract", ErrorKind.PERMANENT)


# ---- 일시 오류 자동 재시도 ----------------------------------------------------
def test_transient_error_retries_then_succeeds(auth_client, mock_dir, db, monkeypatch):
    steps = [ExtractionError("AI 서버 연결 실패", transient=True), good_extraction()]
    doc_id, fake = queue_doc(auth_client, mock_dir, db, monkeypatch, steps)
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.EXTRACTED
    assert doc.attempt_count == 2 and fake.calls == 2


def test_transient_error_stops_after_retry_limit(auth_client, mock_dir, db, monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTION_AUTO_RETRIES", 2)
    doc_id, fake = queue_doc(auth_client, mock_dir, db, monkeypatch, [ConnectionError("끊김")])
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.FAILED
    assert (doc.attempt_count, doc.error_kind) == (3, ErrorKind.TRANSIENT) and fake.calls == 3


def test_retries_can_be_turned_off(auth_client, mock_dir, db, monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTION_AUTO_RETRIES", 0)
    doc_id, fake = queue_doc(auth_client, mock_dir, db, monkeypatch, [ConnectionError("끊김")])
    assert fake.calls == 1 and reload(db, doc_id).status == DocumentStatus.FAILED


# ---- 시간 제한 ---------------------------------------------------------------
def test_timeout_marks_failed_as_transient(auth_client, mock_dir, db, monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTION_TIMEOUT_SEC", 0)
    monkeypatch.setattr(settings, "EXTRACTION_AUTO_RETRIES", 0)
    doc_id, _ = queue_doc(auth_client, mock_dir, db, monkeypatch, [0.3])
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.FAILED
    assert (doc.failed_stage, doc.error_kind) == ("timeout", ErrorKind.TRANSIENT)
    assert "제한 시간" in doc.error_message
    time.sleep(0.4)  # 뒤늦게 끝난 추출 스레드가 결과를 바꾸지 않는다
    assert reload(db, doc_id).status == DocumentStatus.FAILED


# ---- 처리 시작 선점 ----------------------------------------------------------
def test_only_one_worker_claims_a_document(auth_client, mock_dir, db, monkeypatch):
    doc_id, fake = queue_doc(auth_client, mock_dir, db, monkeypatch, [good_extraction()])
    assert fake.calls == 1
    worker.process_document(doc_id)  # 이미 extracted → 다시 처리하지 않는다
    assert fake.calls == 1
    set_status(db, doc_id, DocumentStatus.QUEUED)
    assert worker.claim_document(db, doc_id) is True
    assert worker.claim_document(db, doc_id) is False  # 이미 processing


# ---- 재처리·멈춘 문서 -------------------------------------------------------
def test_manual_retry_resets_attempt_record(auth_client, mock_dir, db, monkeypatch):
    doc_id, _ = queue_doc(auth_client, mock_dir, db, monkeypatch, [ExtractionError("실패")])
    assert reload(db, doc_id).attempt_count == 1
    install(monkeypatch, [good_extraction()])
    assert retry(auth_client, doc_id).status_code == 200
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.EXTRACTED and doc.attempt_count == 1
    assert doc.failed_stage is None and doc.error_kind is None


def test_recover_records_interruption(auth_client, mock_dir, db):
    doc_id = upload_stuck(auth_client, mock_dir, db, attempts=1)
    assert document_service.recover_stuck_documents(db) == 1
    doc = reload(db, doc_id)
    assert doc.status == DocumentStatus.FAILED
    assert (doc.attempt_count, doc.failed_stage, doc.error_kind) == (1, "interrupted", ErrorKind.TRANSIENT)


def test_recover_with_limit_requeues_only_under_limit(auth_client, mock_dir, db):
    low = upload_stuck(auth_client, mock_dir, db, attempts=1)
    high = upload_stuck(auth_client, mock_dir, db, attempts=2)
    assert document_service.list_resumable_documents(db, 2) == [low]
    assert document_service.recover_stuck_documents(db, max_attempts=2) == 1  # 실패로 바뀐 건수는 상한을 넘은 1건
    assert reload(db, low).status == DocumentStatus.QUEUED
    failed = reload(db, high)
    assert failed.status == DocumentStatus.FAILED and failed.failed_stage == "interrupted"


def upload_stuck(client, mock_dir, db, *, attempts: int) -> str:
    """처리 중에 서버가 꺼진 것처럼 문서를 processing 으로 만든다."""
    set_mock(mock_dir, GOOD)
    doc_id = upload(client)
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.PROCESSING
    doc.attempt_count = attempts
    doc.error_message = None
    db.commit()
    return doc_id


def test_detail_exposes_failure_record(auth_client, mock_dir, db, monkeypatch):
    doc_id, _ = queue_doc(auth_client, mock_dir, db, monkeypatch, [ExtractionError("손상된 파일")])
    data = auth_client.get(f"/api/v1/documents/{doc_id}").json()["data"]
    assert (data["attempt_count"], data["failed_stage"], data["error_kind"]) == (1, "extract", "permanent")
