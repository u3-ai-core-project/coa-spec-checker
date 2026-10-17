"""[담당: 장수민] 교차 규칙 테스트 — 중금속 총량 → Pb (명세 v1.4안 2.3), 문서 정합성 오류 → 보류 (v1.4안 2.4)."""
import pytest

from app.core.enums import (
    DocumentIssueCode, Judgement as J, LotRecommendation as L, MappingSource, ReasonCode as R, ResolutionType as T,
)
from app.schemas.extraction import DocumentIssue, ExtractedItem, ExtractionInput
from app.services.judgement.engine import judge_document, refresh_summary
from app.services.judgement.item_judge import evaluate_item
from app.services.judgement.policy import DEFAULT_REASON_JUDGEMENT, JudgementPolicy
from app.services.judgement.spec_rule import SpecRule

POLICY = JudgementPolicy()
NA = SpecRule("Na", unit="ppm", usl=50)
PB = SpecRule("Pb", unit="ppm", usl=3)
TOTAL = SpecRule("중금속 총량", unit="ppm", is_required=False)  # 시드와 같은 방식 (범위 없음, 필수 아님)
SPECS = [NA, PB, TOTAL]


def coa(*items):
    return ExtractionInput(items=list(items))


def row(name, raw_value, unit="ppm", conf=0.95, raw_name=None):
    return ExtractedItem(raw_name=raw_name or name, normalized_name=name, mapping_source=MappingSource.DICTIONARY,
                         raw_value=raw_value, unit=unit, confidence=conf)


def run(*items, specs=SPECS, policy=POLICY, issues=()):
    return judge_document(coa(*items), document_id="d1", specs=specs, policy=policy, issues=issues)


def pb_of(result):
    return next(i for i in result.items if i.normalized_name == "Pb")


# ---- 중금속 총량 → Pb ---------------------------------------------------------
def test_total_within_pb_limit_makes_pb_pass():
    r = run(row("Na", "10"), row("중금속 총량", "2", raw_name="Heavy metals (as Pb)"))
    pb = pb_of(r)
    assert (pb.judgement, pb.reason_code, pb.resolution) == (J.PASS, None, None)
    assert "총량 ≥ 개별값" in pb.judgement_reason
    assert r.lot_recommendation == L.APPROVE   # A0396981 처럼 정상 자동 처리


def test_total_above_pb_limit_is_ambiguous():
    # A0408240: 중금속 10.15 ppm, Pb 상한 3 (기획안 v2 7.2)
    r = run(row("Na", "10"), row("중금속 총량", "10.15"))
    pb = pb_of(r)
    assert (pb.judgement, pb.reason_code) == (J.CHECK, R.AMBIGUOUS_ANALYTE)
    assert (pb.resolution.type, pb.resolution.target_item, pb.resolution.threshold) == (T.SINGLE_VALUE, "Pb", 3)
    assert r.lot_recommendation == L.HOLD


def test_ambiguous_judgement_follows_policy():
    policy = POLICY.with_overrides(reason_judgement={**DEFAULT_REASON_JUDGEMENT, R.AMBIGUOUS_ANALYTE: J.UNDETERMINED})
    assert pb_of(run(row("중금속 총량", "10.15"), policy=policy)).judgement == J.UNDETERMINED


@pytest.mark.parametrize("raw, unit, expected", [
    ("< 1", "ppm", J.PASS),             # 상한값 표기도 상한으로 사용
    ("0.0002 %", None, J.PASS),         # 2 ppm 으로 환산
    ("ND (<1 ppm)", None, J.PASS),      # 검출 안 됨 → 검출한계가 상한
    ("0.002 %", None, J.CHECK),         # 20 ppm > 3
])
def test_total_value_formats(raw, unit, expected):
    assert pb_of(run(row("중금속 총량", raw, unit=unit))).judgement == expected


def test_real_pb_value_takes_priority():
    r = run(row("Pb", "5"), row("중금속 총량", "1"))
    pb = pb_of(r)
    assert (pb.judgement, pb.reason_code) == (J.FAIL, R.OUT_OF_SPEC)  # 총량이 낮아도 실측 Pb 로 판정


def test_no_total_keeps_pb_missing():
    assert pb_of(run(row("Na", "10"))).judgement == J.MISSING


def test_low_confidence_total_is_not_used():
    r = run(row("중금속 총량", "1", conf=0.5))
    assert pb_of(r).judgement == J.MISSING
    total = next(i for i in r.items if i.normalized_name == "중금속 총량")
    assert total.reason_code == R.LOW_CONFIDENCE   # 총량 항목 자체가 확인 필요로 올라감


def test_total_without_spec_entry_still_works():
    # 규격 세트에 "중금속 총량" 을 등록하지 않아도 원문 값을 직접 해석해 적용한다
    assert pb_of(run(row("중금속 총량", "2"), specs=[NA, PB])).judgement == J.PASS


def test_rule_can_be_disabled():
    policy = POLICY.with_overrides(cross_rules=())
    assert pb_of(run(row("중금속 총량", "2"), policy=policy)).judgement == J.MISSING


def test_unknown_rule_name_rejected():
    with pytest.raises(ValueError):
        run(row("Na", "1"), policy=POLICY.with_overrides(cross_rules=("na_k_sum",)))


def test_user_entered_pb_value_is_not_overwritten():
    r = run(row("Na", "10"), row("중금속 총량", "10.15"))
    # 담당자가 Pb 단일값 1 ppm 을 입력해 재판정 (검수 API 가 하는 일)
    from app.services.judgement.value_parser import ParsedValue
    from app.core.enums import ValueQualifier as Q
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "Pb")
    r.items[idx] = evaluate_item(r.items[idx], PB, override=ParsedValue(Q.EXACT, 1), policy=POLICY)
    refresh_summary(r, SPECS, POLICY)
    assert (pb_of(r).judgement, pb_of(r).converted_value) == (J.PASS, 1)
    assert r.lot_recommendation == L.APPROVE


# ---- 재계산 (refresh_summary) ------------------------------------------------
def test_refresh_is_idempotent():
    r = run(row("Na", "10"), row("중금속 총량", "2"))
    before = r.model_dump()
    refresh_summary(r, SPECS, POLICY)
    refresh_summary(r, SPECS, POLICY)
    assert r.model_dump() == before


def test_refresh_reapplies_rule_after_total_edit():
    r = run(row("Na", "10"), row("중금속 총량", "2"))
    assert pb_of(r).judgement == J.PASS
    # 담당자가 총량 값을 20 ppm 으로 수정
    from app.services.judgement.value_parser import ParsedValue
    from app.core.enums import ValueQualifier as Q
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "중금속 총량")
    r.items[idx] = evaluate_item(r.items[idx], TOTAL, override=ParsedValue(Q.EXACT, 20), policy=POLICY)
    refresh_summary(r, SPECS, POLICY)
    assert (pb_of(r).reason_code, r.lot_recommendation) == (R.AMBIGUOUS_ANALYTE, L.HOLD)


def test_refresh_restores_missing_when_total_becomes_unusable():
    r = run(row("중금속 총량", "2"))
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "중금속 총량")
    r.items[idx] = r.items[idx].model_copy(update={"reason_code": R.LOW_CONFIDENCE, "judgement": J.CHECK})
    refresh_summary(r, SPECS, POLICY)
    assert (pb_of(r).judgement, pb_of(r).reason_code) == (J.MISSING, R.MISSING_REQUIRED)


# ---- 문서 정합성 오류 → 보류 (v1.4안 2.4) ---------------------------------------
def test_document_issue_makes_hold_even_if_all_pass():
    issue = DocumentIssue(code=DocumentIssueCode.LOT_MISMATCH, message="CoA 로트 A1 ≠ 입고 로트 B2")
    r = run(row("Na", "10"), row("중금속 총량", "1"), issues=[issue])
    assert r.summary.fail == 0 and r.lot_recommendation == L.HOLD
    assert r.document_issues[0].code == DocumentIssueCode.LOT_MISMATCH


def test_fail_outranks_document_issue():
    issue = DocumentIssue(code=DocumentIssueCode.DATE_CONFLICT, message="유효기한 경과")
    assert run(row("Na", "80"), issues=[issue]).lot_recommendation == L.REJECT


def test_result_json_has_new_fields():
    data = run(row("Na", "80"), row("중금속 총량", "1")).to_json()
    na = next(i for i in data["items"] if i["normalized_name"] == "Na")
    assert na["reason_code"] == "OUT_OF_SPEC" and na["resolution"]["type"] == "confirm"
    assert data["document_issues"] == []
