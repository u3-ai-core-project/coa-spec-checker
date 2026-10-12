"""[담당: 장수민] enum 값이 명세 문자열과 같은지 확인 (프론트·AI 파트와의 계약)."""
from app.core.enums import (
    DocumentStatus, FinalDecision, Judgement, LotRecommendation, ReviewStatus,
    ValueQualifier, status_to_review_status,
)


def test_values_match_spec():
    assert {s.value for s in DocumentStatus} == {
        "queued", "processing", "extracted", "in_review", "on_hold", "approved", "failed"}
    assert {j.value for j in Judgement} == {"pass", "fail", "undetermined", "missing", "check"}
    assert {r.value for r in LotRecommendation} == {"approve", "hold", "reject"}
    assert {d.value for d in FinalDecision} == {"accept", "conditional_accept", "reject"}
    assert {q.value for q in ValueQualifier} == {"exact", "less_than", "less_equal", "not_detected", "text"}


def test_review_status_sync():
    assert status_to_review_status(DocumentStatus.EXTRACTED) == ReviewStatus.PENDING
    assert status_to_review_status(DocumentStatus.IN_REVIEW) == ReviewStatus.IN_REVIEW
    assert status_to_review_status(DocumentStatus.ON_HOLD) == ReviewStatus.ON_HOLD
    assert status_to_review_status(DocumentStatus.APPROVED) == ReviewStatus.APPROVED
