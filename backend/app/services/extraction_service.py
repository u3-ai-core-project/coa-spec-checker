"""[담당: 장수민] AI 추출 결과 수신 → 판정 → extraction_results 저장, 문서 상태 전이.

AI 추출 파트의 결과가 들어오는 입구는 save_extraction() 하나다.
"""
from sqlalchemy.orm import Session

from app.core.enums import DocumentStatus, status_to_review_status
from app.models import Document, ExtractionResult as ExtractionResultRow
from app.schemas.extraction import ExtractionInput, ExtractionResult
from app.services import batch_service, spec_service
from app.services.judgement.document_checks import check_document
from app.services.judgement.engine import judge_document

MSG_NO_ITEMS = "문서에서 시험 항목을 찾을 수 없습니다"


class EmptyExtractionError(ValueError):
    pass


def save_extraction(db: Session, document: Document, extraction: ExtractionInput) -> ExtractionResult:
    """추출 결과를 판정해 저장하고 문서를 extracted 로 바꾼다. commit 은 호출한 쪽에서 한다."""
    if not extraction.items:
        raise EmptyExtractionError(MSG_NO_ITEMS)

    # 일괄 접수 문서는 CoA 로트로 입고 정보와 연결한다 (UC01·UC07). 연결되면 입고 행의 규격 세트로 바뀔 수 있어 먼저 한다
    batch_issues = batch_service.link_by_lot(db, document, extraction)
    spec_set = document.spec_set or spec_service.get_default_set(db, document.material_code)
    specs = spec_service.get_rules(db, spec_set.id) if spec_set else []
    # 문서 정합성 검사 (v1.4 2.1, 데모 12·18): 입고 로트 ≠ CoA 로트, 날짜 충돌(입고일 포함), 규격 버전 다름 → 보류 권고
    receipt = batch_service.receipt_of(db, document)
    issues = check_document(extraction, received_lot_no=document.received_lot_no,
                            spec_version=spec_set.version if spec_set else None,
                            received_date=receipt.received_date if receipt else None) + batch_issues
    result = judge_document(extraction, document_id=document.id, specs=specs, issues=issues)

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


def sync_review_status(document: Document) -> None:
    """documents.status 가 바뀐 뒤 JSON 의 review_status 를 맞춘다 (명세 2.1: 기준은 documents.status)."""
    if document.extraction is not None:
        document.extraction.result["review_status"] = status_to_review_status(document.status).value


def get_result(document: Document) -> ExtractionResult | None:
    if document.extraction is None:
        return None
    return ExtractionResult.model_validate(document.extraction.result)
