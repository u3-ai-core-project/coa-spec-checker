"""[담당: 장수민] 문서 1건 처리: queued → processing → extracted / failed.

업로드 API 가 FastAPI BackgroundTasks 로 process_document(document_id) 를 등록한다.
요청과 다른 시점에 실행되므로 DB 세션을 직접 연다.
"""
import logging
from pathlib import Path

from app.core.enums import DocumentStatus
from app.db.session import SessionLocal
from app.models import Document
from app.pipeline.extractor import ExtractionError, get_extractor
from app.services import extraction_service

logger = logging.getLogger(__name__)

MSG_UNEXPECTED = "추출 처리 중 오류가 발생했습니다"


def process_document(document_id: str) -> None:
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None or doc.status != DocumentStatus.QUEUED:
            return
        doc.status = DocumentStatus.PROCESSING
        db.commit()

        try:
            extraction = get_extractor().extract(
                Path(doc.file_path), material_code=doc.material_code, original_name=doc.file_name
            )
            extraction_service.save_extraction(db, doc, extraction)
        except (ExtractionError, extraction_service.EmptyExtractionError) as e:
            db.rollback()
            extraction_service.mark_failed(doc, str(e))
        except Exception:
            logger.exception("문서 처리 실패: %s", document_id)
            db.rollback()
            extraction_service.mark_failed(doc, MSG_UNEXPECTED)
        db.commit()
