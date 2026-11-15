"""[담당: 고도영] AI 추출 입력의 문서 필드 (PR #5 요청: 제품 불일치·날짜 충돌 document_issues 탐지용)."""
from datetime import date

from app.schemas.extraction import ExtractionInput, ExtractionResult
from app.services.judgement.engine import judge_document

RAW = {
    "supplier": "RUILAN LITHIUM (YICHUN) CO., LTD.", "lot_no": "LC25100401", "test_date": "2025-10-05",
    "product_name": "电池级碳酸锂 Battery Grade Lithium Carbonate", "issue_date": "2025-10-07",
    "expiry_date": "2026-10-04", "retest_date": None,
    "items": [{"normalized_name": "Na", "raw_value": "0.0044", "unit": "%"}],
}


def test_extraction_input_reads_document_fields():
    e = ExtractionInput.model_validate(RAW)
    assert (e.issue_date, e.expiry_date, e.retest_date) == (date(2025, 10, 7), date(2026, 10, 4), None)
    assert e.product_name.endswith("Lithium Carbonate")


def test_fields_are_optional():
    e = ExtractionInput.model_validate({"items": RAW["items"]})
    assert (e.product_name, e.issue_date, e.expiry_date, e.retest_date) == (None, None, None, None)


def test_judged_result_keeps_document_fields():
    # 판정 결과 JSON(extraction_results.result)과 GET /documents/{id}/extraction 에 남아야 서버 검사가 읽을 수 있다
    result = judge_document(ExtractionInput.model_validate(RAW), document_id="doc-1", specs=[])
    saved = result.to_json()
    assert (saved["issue_date"], saved["expiry_date"], saved["retest_date"]) == ("2025-10-07", "2026-10-04", None)
    assert ExtractionResult.model_validate(saved).product_name == RAW["product_name"]
