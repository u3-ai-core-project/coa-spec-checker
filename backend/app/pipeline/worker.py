"""[담당: 장수민] 문서 1건 처리: queued → processing → extracted / failed (운영 정책 4장).

업로드 API 가 FastAPI BackgroundTasks 로 process_document(document_id) 를 등록한다.
요청과 다른 시점에 실행되므로 DB 세션을 직접 연다.

- 처리를 시작할 때 "queued 이면 processing 으로 바꾸기" 를 DB 한 문장으로 한다. 같은 문서를 두 곳에서 동시에 시작해도 한 곳만 통과한다.
- 추출 1회는 EXTRACTION_TIMEOUT_SEC (기본 5분) 안에 끝나야 한다. 넘으면 실패로 처리한다.
  제한 시간을 넘긴 추출 스레드는 멈출 수 없으므로 뒤에서 끝나도 결과는 버린다.
- 실패하면 시도 횟수, 실패 단계, 오류 종류(영구·일시)를 문서에 남긴다.
  일시 오류는 EXTRACTION_AUTO_RETRIES 만큼 자동으로 다시 시도하고, 영구 오류는 바로 실패로 둔다.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update

from app.core.config import settings
from app.core.safe_log import log_exception
from app.core.enums import DocumentStatus, ErrorKind, FailStage
from app.db.session import SessionLocal
from app.models import Document
from app.pipeline.extractor import ExtractionError, get_extractor
from app.schemas.extraction import ExtractionInput
from app.services import extraction_service

logger = logging.getLogger(__name__)

MSG_UNEXPECTED = "추출 처리 중 오류가 발생했습니다"
MSG_TIMEOUT = "추출이 제한 시간({minutes}분)을 넘겨 중단되었습니다. 다시 처리해 주세요"


class ExtractionTimeout(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_document(db, document_id: str) -> bool:
    """queued → processing. 이 문서를 맡았으면 True. 시도 횟수를 1 늘리고 시작 시각을 남긴다."""
    claimed = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.status == DocumentStatus.QUEUED)
        .values(status=DocumentStatus.PROCESSING, attempt_count=Document.attempt_count + 1,
                processing_started_at=_now(), processing_finished_at=None, failed_stage=None, error_kind=None)
    )
    db.commit()
    return claimed.rowcount == 1


def _extract_with_timeout(doc: Document) -> ExtractionInput:
    path, material, name = Path(doc.file_path), doc.material_code, doc.file_name
    timeout = settings.EXTRACTION_TIMEOUT_SEC
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(lambda: get_extractor().extract(path, material_code=material, original_name=name))
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            raise ExtractionTimeout from None
    finally:
        pool.shutdown(wait=False)  # 시간을 넘긴 스레드를 기다리지 않는다


def process_document(document_id: str) -> None:
    with SessionLocal() as db:
        if not claim_document(db, document_id):
            return
        doc = db.get(Document, document_id)
        retries_left = max(settings.EXTRACTION_AUTO_RETRIES, 0)

        while True:
            failure: tuple[str, FailStage, ErrorKind] | None = None
            try:
                extraction = _extract_with_timeout(doc)
            except ExtractionTimeout:
                minutes = max(settings.EXTRACTION_TIMEOUT_SEC // 60, 1)
                failure = (MSG_TIMEOUT.format(minutes=minutes), FailStage.TIMEOUT, ErrorKind.TRANSIENT)
            except ExtractionError as e:
                kind = ErrorKind.TRANSIENT if e.transient else ErrorKind.PERMANENT
                failure = (str(e), FailStage.EXTRACT, kind)
            except (ConnectionError, TimeoutError) as e:
                logger.warning("문서 추출 연결 오류: %s (%s)", document_id, type(e).__name__)
                failure = (MSG_UNEXPECTED, FailStage.EXTRACT, ErrorKind.TRANSIENT)
            except Exception as e:
                log_exception(logger, "문서 추출 실패: %s", document_id, exc=e)
                failure = (MSG_UNEXPECTED, FailStage.EXTRACT, ErrorKind.PERMANENT)
            else:
                try:
                    extraction_service.save_extraction(db, doc, extraction)
                    doc.processing_finished_at = _now()
                    db.commit()
                    return
                except extraction_service.EmptyExtractionError as e:
                    db.rollback()
                    failure = (str(e), FailStage.EXTRACT, ErrorKind.PERMANENT)
                except Exception as e:
                    log_exception(logger, "문서 판정·저장 실패: %s", document_id, exc=e)
                    db.rollback()
                    failure = (MSG_UNEXPECTED, FailStage.JUDGE, ErrorKind.PERMANENT)

            message, stage, kind = failure
            if kind == ErrorKind.TRANSIENT and retries_left > 0:
                retries_left -= 1
                logger.info("일시 오류로 다시 시도합니다: %s (%s)", document_id, stage)
                doc.attempt_count += 1
                doc.processing_started_at = _now()
                db.commit()
                continue
            extraction_service.mark_failed(doc, message, stage=stage, kind=kind)
            doc.processing_finished_at = _now()
            db.commit()
            return
