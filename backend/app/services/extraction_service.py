"""[담당: 장수민] AI 추출 결과 수신 → 판정 → extraction_results 저장, 문서 상태 전이.

AI 추출 파트의 결과가 들어오는 입구는 save_extraction() 하나다.
"""
from sqlalchemy.orm import Session

from app.core.enums import DocumentStatus
from app.models import Document, ExtractionResult as ExtractionResultRow
from app.schemas.extraction import ExtractionInput, ExtractionResult
from app.services import spec_service
from app.services.judgement.engine import judge_document

MSG_NO_ITEMS = "문서에서 시험 항목을 찾을 수 없습니다"


class EmptyExtractionError(ValueError):
    pass


def save_extraction(db: Session, document: Document, extraction: ExtractionInput) -> ExtractionResult:
    """추출 결과를 판정해 저장하고 문서를 extracted 로 바꾼다. commit 은 호출한 쪽에서 한다."""
    if not extraction.items:
        raise EmptyExtractionError(MSG_NO_ITEMS)

    specs = spec_service.get_rules(db, document.material_code)
    result = judge_document(extraction, document_id=document.id, specs=specs)

    # 업로드 때 입력한 협력사명이 있으면 그것을 우선한다
    document.supplier = document.supplier or extraction.supplier
    document.lot_no = extraction.lot_no
    document.test_date = extraction.test_date
    document.origin = extraction.origin
    document.applied_standard = extraction.applied_standard
    document.lot_recommendation = result.lot_recommendation
    document.status = DocumentStatus.EXTRACTED
    document.error_message = None

    if document.extraction is None:
        document.extraction = ExtractionResultRow(result=result.to_json())
    else:
        document.extraction.result = result.to_json()
    return result


def mark_failed(document: Document, message: str) -> None:
    document.status = DocumentStatus.FAILED
    document.error_message = message


def get_result(document: Document) -> ExtractionResult | None:
    if document.extraction is None:
        return None
    return ExtractionResult.model_validate(document.extraction.result)
