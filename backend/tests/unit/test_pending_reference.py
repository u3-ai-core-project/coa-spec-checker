"""[담당: 장수민] 처분 차단 검사에서 참고 항목 제외 (10.25 회의 결정 8)."""
from types import SimpleNamespace

from app.schemas.extraction import ExtractionInput
from app.services.approval_service import pending_low_confidence_items
from app.services.judgement.engine import judge_document
from app.services.judgement.spec_rule import SpecRule

NA = SpecRule("Na", unit="ppm", usl=50)


def _doc(items: list[dict]) -> SimpleNamespace:
    """DB 없이 판정 결과 JSON 만 가진 문서 대용."""
    result = judge_document(ExtractionInput.model_validate({"items": items}), document_id="doc-1", specs=[NA])
    return SimpleNamespace(extraction=SimpleNamespace(result=result.to_json()))


def test_low_confidence_spec_item_blocks():
    doc = _doc([{"normalized_name": "Na", "raw_value": "30", "unit": "ppm", "confidence": 0.5}])
    assert pending_low_confidence_items(doc) == ["Na"]


def test_low_confidence_reference_item_does_not_block():
    # B 는 사내 규격에 없는 참고 항목. 신뢰도가 낮아도 처분을 막지 않는다.
    doc = _doc([
        {"normalized_name": "Na", "raw_value": "30", "unit": "ppm", "confidence": 0.95},
        {"normalized_name": "B", "raw_value": "5", "unit": "ppm", "confidence": 0.3, "mapping_source": "dictionary"},
    ])
    assert pending_low_confidence_items(doc) == []


def test_low_confidence_unmapped_ai_item_still_blocks():
    # AI 가 추정한 미등록 항목명은 참고가 아니라 확인 필요(UNMAPPED_ITEM)라 계속 막는다.
    doc = _doc([{"normalized_name": "Xyz", "raw_value": "5", "unit": "ppm", "confidence": 0.3, "mapping_source": "ai"}])
    assert pending_low_confidence_items(doc) == ["Xyz"]


def test_reviewed_low_confidence_item_does_not_block():
    doc = _doc([{"normalized_name": "Na", "raw_value": "30", "unit": "ppm", "confidence": 0.5}])
    doc.extraction.result["items"][0]["reviewed"] = True
    assert pending_low_confidence_items(doc) == []
