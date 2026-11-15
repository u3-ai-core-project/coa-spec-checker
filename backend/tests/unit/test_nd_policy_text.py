"""[담당: 장수민] 검출 안 됨 정책 문구 (10.25 회의 결정 6)."""
from app.schemas.extraction import ExtractionInput
from app.services.judgement.engine import judge_document
from app.services.judgement.policy import JudgementPolicy
from app.services.judgement.spec_rule import SpecRule

FE = SpecRule("Fe", unit="ppm", usl=5)


def fe_reason(raw: str, policy=None) -> str:
    inp = ExtractionInput.model_validate({"items": [
        {"normalized_name": "Fe", "raw_value": raw, "unit": "ppm", "confidence": 0.95, "mapping_source": "dictionary"}]})
    item = judge_document(inp, document_id="d", specs=[FE], policy=policy).items[0]
    assert item.judgement == "pass"
    return item.judgement_reason


def test_nd_pass_states_policy():
    assert "정책: 검출한계 ≤ 사내 상한이면 적합" in fe_reason("ND (LOD 2 ppm)")


def test_nd_pass_at_boundary_states_policy():
    assert "정책: 검출한계 ≤ 사내 상한이면 적합" in fe_reason("ND (LOD 5 ppm)")


def test_nd_pass_below_limit_with_exclusive_policy_says_less_than():
    p = JudgementPolicy().with_overrides(nd_limit_inclusive=False)
    assert "정책: 검출한계 < 사내 상한이면 적합" in fe_reason("ND (LOD 2 ppm)", p)
