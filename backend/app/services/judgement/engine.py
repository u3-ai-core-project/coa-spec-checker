"""[담당: 장수민] 문서 1건 전체 판정. DB 를 쓰지 않는 순수 함수.

사용처
  - extraction_service : AI 결과 수신 직후 judge_document()
  - review_service     : 항목 1개를 evaluate_item() 으로 다시 판정한 뒤 refresh_summary()
"""
from collections.abc import Iterable

from app.core.config import settings
from app.core.enums import ReviewStatus
from app.schemas.extraction import ExtractionInput, ExtractionResult
from app.services.judgement.item_judge import evaluate_item
from app.services.judgement.lot_recommend import recommend, summarize
from app.services.judgement.missing_items import build_missing_items
from app.services.judgement.spec_rule import SpecRule, name_key


def judge_document(
    extraction: ExtractionInput,
    *,
    document_id: str,
    specs: Iterable[SpecRule],
    threshold: float | None = None,
    oxide_factors: dict[str, float] | None = None,
) -> ExtractionResult:
    """AI 추출 결과 + 해당 원자재의 사내 규격 → 판정까지 채운 결과."""
    threshold = settings.LOW_CONFIDENCE_THRESHOLD if threshold is None else threshold
    specs = list(specs)
    by_name = {name_key(s.item_name): s for s in specs}

    extracted = [
        i if i.item_id else i.model_copy(update={"item_id": f"item-{n:03d}"})
        for n, i in enumerate(extraction.items, start=1)
    ]
    candidates = extracted + build_missing_items(extracted, specs)

    items = [
        evaluate_item(i, by_name.get(name_key(i.normalized_name)), threshold=threshold, oxide_factors=oxide_factors)
        for i in candidates
    ]
    summary = summarize(items)

    return ExtractionResult(
        document_id=document_id,
        supplier=extraction.supplier,
        lot_no=extraction.lot_no,
        test_date=extraction.test_date,
        origin=extraction.origin,
        applied_standard=extraction.applied_standard,
        items=items,
        lot_recommendation=recommend(summary),
        summary=summary,
        review_status=ReviewStatus.PENDING,
    )


def refresh_summary(result: ExtractionResult) -> ExtractionResult:
    """항목이 바뀐 뒤 summary 와 lot_recommendation 을 다시 계산 (명세 4.9). result 를 직접 고친다."""
    result.summary = summarize(result.items)
    result.lot_recommendation = recommend(result.summary)
    return result
