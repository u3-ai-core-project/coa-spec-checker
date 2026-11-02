"""[담당: 장수민] 문서 1건 전체 판정. DB 를 쓰지 않는 순수 함수.

흐름
  1. 항목별 판정 (item_judge.evaluate_item)       — 사유코드·판정·해결 조건
  2. 누락 항목 생성 (missing_items)                — 필수 규격 항목 중 CoA 에 없는 것
  3. 교차 규칙 (cross_rules)                       — 중금속 총량 → Pb 등, 정책에서 켠 것만
  4. 집계와 로트 권고 (lot_recommend)              — document_issues 가 있으면 보류

사용처
  - extraction_service : AI 결과 수신 직후 judge_document()
  - review_service     : 항목 1개를 evaluate_item() 으로 다시 판정한 뒤 refresh_summary(result, specs)
  - 평가 스크립트      : DB 없이 정답 라벨 JSON + 규격으로 judge_document() 를 바로 호출할 수 있다
                         (정책을 바꿔 가며 비교하려면 policy=JudgementPolicy(...).with_overrides(...))
"""
from collections.abc import Iterable

from app.core.enums import ReviewStatus
from app.schemas.extraction import DocumentIssue, ExtractionInput, ExtractionResult
from app.services.judgement.cross_rules import apply_cross_rules
from app.services.judgement.item_judge import evaluate_item
from app.services.judgement.lot_recommend import recommend, summarize
from app.services.judgement.missing_items import build_missing_items
from app.services.judgement.policy import JudgementPolicy, default_policy
from app.services.judgement.spec_rule import SpecRule, name_key


def judge_document(
    extraction: ExtractionInput,
    *,
    document_id: str,
    specs: Iterable[SpecRule],
    threshold: float | None = None,
    oxide_factors: dict[str, float] | None = None,
    policy: JudgementPolicy | None = None,
    issues: Iterable[DocumentIssue] = (),
) -> ExtractionResult:
    """AI 추출 결과 + 문서에 연결된 규격 세트 → 판정까지 채운 결과.

    threshold : 신뢰도 기준값 (None 이면 정책 값). 기존 호출 호환용
    policy    : 판정 정책 (None 이면 현재 설정 기준)
    issues    : 문서 정합성 오류 (P1 의 로트·제품·날짜 검사 결과를 넘길 자리). 1개 이상이면 보류 권고
    """
    policy = policy or default_policy()
    if threshold is not None:
        policy = policy.with_overrides(threshold=threshold)
    specs = list(specs)
    by_name = {name_key(s.item_name): s for s in specs}

    extracted = [
        i if i.item_id else i.model_copy(update={"item_id": f"item-{n:03d}"})
        for n, i in enumerate(extraction.items, start=1)
    ]
    candidates = extracted + build_missing_items(extracted, specs)

    items = [
        evaluate_item(i, by_name.get(name_key(i.normalized_name)), oxide_factors=oxide_factors, policy=policy)
        for i in candidates
    ]
    items = apply_cross_rules(items, by_name, policy)
    issues = list(issues)
    summary = summarize(items)

    return ExtractionResult(
        document_id=document_id,
        supplier=extraction.supplier,
        lot_no=extraction.lot_no,
        test_date=extraction.test_date,
        origin=extraction.origin,
        applied_standard=extraction.applied_standard,
        product_name=extraction.product_name,
        manufacture_date=extraction.manufacture_date,
        issue_date=extraction.issue_date,
        expiry_date=extraction.expiry_date,
        retest_date=extraction.retest_date,
        items=items,
        document_issues=issues,
        lot_recommendation=recommend(summary, issues),
        summary=summary,
        review_status=ReviewStatus.PENDING,
    )


def refresh_summary(
    result: ExtractionResult,
    specs: Iterable[SpecRule] | None = None,
    policy: JudgementPolicy | None = None,
) -> ExtractionResult:
    """항목이 바뀐 뒤 교차 규칙·summary·lot_recommendation 을 다시 계산 (명세 4.9). result 를 직접 고친다.

    specs 를 주면 교차 규칙도 다시 돌린다 (예: 중금속 총량 값을 고치면 Pb 판정도 바뀜).
    검수 API(review_service)에서는 문서의 규격 세트를 넘겨야 한다. 생략하면 교차 규칙은 건너뛴다.
    """
    if specs is not None:
        policy = policy or default_policy()
        by_name = {name_key(s.item_name): s for s in specs}
        result.items = apply_cross_rules(result.items, by_name, policy)
    result.summary = summarize(result.items)
    result.lot_recommendation = recommend(result.summary, result.document_issues)
    return result
