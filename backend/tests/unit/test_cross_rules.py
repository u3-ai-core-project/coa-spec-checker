"""[담당: 장수민] 교차 규칙 테스트 — 중금속 총량 → Pb·Cu, Na+K 합산 → Na·K (명세 v1.4 2.3), 문서 정합성 오류 → 보류 (v1.4 2.4)."""
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
        run(row("Na", "1"), policy=POLICY.with_overrides(cross_rules=("no_such_rule",)))


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


# ---- 중금속 총량 → 다른 중금속 (Cu, 10.25 회의 결정 6) -----------------------------
CU = SpecRule("Cu", unit="ppm", usl=3)                      # 생성기 v2 평가 세트처럼 Cu 가 필수
CU_OPTIONAL = SpecRule("Cu", unit="ppm", usl=5, is_required=False)  # D3·2013 세트처럼 Cu 가 선택


def cu_of(result):
    return next(i for i in result.items if i.normalized_name == "Cu")


@pytest.mark.parametrize("total", ["0.5", "2", "10.15"])
def test_cu_missing_with_total_is_ambiguous_regardless_of_value(total):
    """Pb 기준 총량으로는 Cu 상한을 판단할 수 없어 총량 값과 관계없이 확인 필요 (생성기 v2 AMBIGUOUS_ANALYTE)."""
    r = run(row("Na", "10"), row("중금속 총량", total, raw_name="Heavy metals (as Pb)"), specs=[NA, CU, TOTAL])
    cu = cu_of(r)
    assert (cu.judgement, cu.reason_code) == (J.CHECK, R.AMBIGUOUS_ANALYTE)
    assert (cu.resolution.type, cu.resolution.target_item) == (T.SINGLE_VALUE, "Cu")
    assert "Cu 단일값을 알 수 없음" in cu.judgement_reason
    assert r.lot_recommendation == L.HOLD


def test_cu_and_pb_together():
    """Pb·Cu 둘 다 필수이고 총량 2 ppm 만 있으면 Pb 는 적합(총량 ≤ Pb 상한), Cu 는 확인 필요."""
    r = run(row("중금속 총량", "2"), specs=[PB, CU, TOTAL])
    assert (pb_of(r).judgement, pb_of(r).reason_code) == (J.PASS, None)
    assert cu_of(r).reason_code == R.AMBIGUOUS_ANALYTE


def test_cu_without_total_stays_missing():
    r = run(row("Na", "10"), specs=[NA, CU, TOTAL])
    assert (cu_of(r).judgement, cu_of(r).reason_code) == (J.MISSING, R.MISSING_REQUIRED)


def test_cu_value_on_coa_is_judged_normally():
    r = run(row("Cu", "1"), row("중금속 총량", "2"), specs=[CU, TOTAL])
    assert (cu_of(r).judgement, cu_of(r).reason_code) == (J.PASS, None)


def test_optional_cu_not_flagged():
    """Cu 가 선택 항목이면(D3·2013 세트) 누락 항목이 없어 규칙도 적용하지 않는다."""
    r = run(row("Na", "10"), row("중금속 총량", "2"), specs=[NA, CU_OPTIONAL, TOTAL])
    assert all(i.normalized_name != "Cu" for i in r.items)
    assert r.lot_recommendation == L.APPROVE


def test_pb_only_specs_unchanged_by_cu_rule():
    """Pb 만 있는 기존 세트(D1 등)는 Cu 규칙을 켜도 결과가 그대로다."""
    for total, expected in [("2", (J.PASS, None)), ("10.15", (J.CHECK, R.AMBIGUOUS_ANALYTE))]:
        with_cu_rule = run(row("Na", "10"), row("중금속 총량", total))
        without = run(row("Na", "10"), row("중금속 총량", total), policy=POLICY.with_overrides(heavy_metal_other_names=()))
        assert (pb_of(with_cu_rule).judgement, pb_of(with_cu_rule).reason_code) == expected
        assert with_cu_rule.model_dump() == without.model_dump()


def test_user_entered_cu_value_is_not_overwritten():
    from app.core.enums import ValueQualifier as Q
    from app.services.judgement.value_parser import ParsedValue
    specs = [CU, TOTAL]
    r = run(row("중금속 총량", "2"), specs=specs)
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "Cu")
    r.items[idx] = evaluate_item(r.items[idx], CU, override=ParsedValue(Q.EXACT, 1), policy=POLICY)
    refresh_summary(r, specs, POLICY)
    assert (cu_of(r).judgement, cu_of(r).converted_value) == (J.PASS, 1)


def test_refresh_restores_cu_missing_when_total_becomes_unusable():
    specs = [CU, TOTAL]
    r = run(row("중금속 총량", "2"), specs=specs)
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "중금속 총량")
    r.items[idx] = r.items[idx].model_copy(update={"reason_code": R.LOW_CONFIDENCE, "judgement": J.CHECK})
    refresh_summary(r, specs, POLICY)
    assert (cu_of(r).judgement, cu_of(r).reason_code) == (J.MISSING, R.MISSING_REQUIRED)
    refresh_summary(r, specs, POLICY)
    assert cu_of(r).reason_code == R.MISSING_REQUIRED      # 다시 돌려도 같음


# ---- Na+K 합산 → Na, K (원소별, 10.25 회의 결정 2, 멘토님 데모 15) ----------------------
K = SpecRule("K", unit="ppm", usl=10)
NA_K_SPECS = [NA, K]                                         # D1 처럼 Na ≤ 50, K ≤ 10


def item_of(result, name):
    return next(i for i in result.items if i.normalized_name == name)


def na_k(raw_value, unit="ppm", **kw):
    return row("Na+K", raw_value, unit=unit, **kw)


def test_sum_judged_per_element():
    """데모 15: Na+K 40 ppm → Na(≤ 50) 적합, K(≤ 10) 만 SUM_ONLY. 합산값을 나눠 추정하지 않는다."""
    r = run(na_k("40"), specs=NA_K_SPECS)
    na, k = item_of(r, "Na"), item_of(r, "K")
    assert (na.judgement, na.reason_code, na.resolution) == (J.PASS, None, None)
    assert "합산 ≥ 개별값" in na.judgement_reason
    assert (k.judgement, k.reason_code) == (J.CHECK, R.SUM_ONLY)
    assert (k.resolution.type, k.resolution.target_item) == (T.SINGLE_VALUE, "K")
    assert "K 개별값을 알 수 없음" in k.judgement_reason
    assert k.converted_value is None                         # 개별값을 만들어 넣지 않는다
    assert r.lot_recommendation == L.HOLD


def test_small_sum_passes_both():
    r = run(na_k("8"), specs=NA_K_SPECS)
    assert (item_of(r, "Na").judgement, item_of(r, "K").judgement) == (J.PASS, J.PASS)
    assert r.lot_recommendation == L.APPROVE


def test_sum_above_both_limits():
    r = run(na_k("60"), specs=NA_K_SPECS)
    assert (item_of(r, "Na").reason_code, item_of(r, "K").reason_code) == (R.SUM_ONLY, R.SUM_ONLY)


def test_sum_equal_to_limit_passes():
    assert item_of(run(na_k("10"), specs=NA_K_SPECS), "K").judgement == J.PASS


@pytest.mark.parametrize("raw, unit, expected_k", [
    ("< 5", "ppm", J.PASS),             # 상한값 표기도 상한으로 사용
    ("0.0008 %", None, J.PASS),         # 8 ppm 으로 환산
    ("ND (<5 ppm)", None, J.PASS),      # 검출 안 됨 → 검출한계가 상한
    ("0.004 %", None, J.CHECK),         # 40 ppm > K 상한 10
])
def test_sum_value_formats(raw, unit, expected_k):
    assert item_of(run(na_k(raw, unit=unit), specs=NA_K_SPECS), "K").judgement == expected_k


def test_sum_only_judgement_follows_policy():
    policy = POLICY.with_overrides(reason_judgement={**DEFAULT_REASON_JUDGEMENT, R.SUM_ONLY: J.UNDETERMINED})
    assert item_of(run(na_k("40"), specs=NA_K_SPECS, policy=policy), "K").judgement == J.UNDETERMINED


def test_element_on_coa_is_judged_normally():
    """Na 개별값이 있으면 Na 는 그 값으로, 없는 K 만 합산으로 본다 (합산 - Na 로 계산하지 않음)."""
    r = run(row("Na", "30"), na_k("38"), specs=NA_K_SPECS)
    assert (item_of(r, "Na").judgement, item_of(r, "Na").converted_value) == (J.PASS, 30)
    assert item_of(r, "K").reason_code == R.SUM_ONLY        # 38 - 30 = 8 ≤ 10 으로 보지 않는다


def test_no_sum_keeps_elements_missing():
    r = run(row("Fe", "1"), specs=NA_K_SPECS)
    assert (item_of(r, "Na").judgement, item_of(r, "K").judgement) == (J.MISSING, J.MISSING)


@pytest.mark.parametrize("sum_row", [
    na_k("8", conf=0.5),                                     # 신뢰도 낮음
    na_k("ND"),                                              # 검출한계 미기재
    na_k("abc"),                                             # 값 해석 실패
    na_k("≤ 10").model_copy(update={"raw_spec": "≤ 10"}),    # 결과 칸 = 규격 문구
])
def test_unusable_sum_keeps_elements_missing(sum_row):
    r = run(sum_row, specs=NA_K_SPECS)
    assert (item_of(r, "Na").reason_code, item_of(r, "K").reason_code) == (R.MISSING_REQUIRED, R.MISSING_REQUIRED)


def test_sum_row_itself_is_reference():
    """합산 줄은 사내 규격 항목이 아니라 참고. 판정은 Na, K 에만 붙는다."""
    s = item_of(run(na_k("40"), specs=NA_K_SPECS), "Na+K")
    assert (s.judgement, s.reason_code) == (J.PASS, None)


def test_optional_element_not_flagged():
    k_optional = SpecRule("K", unit="ppm", usl=10, is_required=False)
    r = run(na_k("40"), specs=[NA, k_optional])
    assert item_of(r, "Na").judgement == J.PASS
    assert all(i.normalized_name != "K" for i in r.items)
    assert r.lot_recommendation == L.APPROVE


def test_na_k_rule_can_be_disabled():
    r = run(na_k("40"), specs=NA_K_SPECS, policy=POLICY.with_overrides(cross_rules=("heavy_metal_total",)))
    assert (item_of(r, "Na").judgement, item_of(r, "K").judgement) == (J.MISSING, J.MISSING)


def test_sum_name_follows_policy():
    policy = POLICY.with_overrides(na_k_sum_name="Na+K 합량")
    r = run(row("Na+K 합량", "40"), specs=NA_K_SPECS, policy=policy)
    assert item_of(r, "K").reason_code == R.SUM_ONLY


def test_user_entered_k_value_is_not_overwritten():
    from app.core.enums import ValueQualifier as Q
    from app.services.judgement.value_parser import ParsedValue
    r = run(na_k("40"), specs=NA_K_SPECS)
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "K")
    r.items[idx] = evaluate_item(r.items[idx], K, override=ParsedValue(Q.EXACT, 3), policy=POLICY)
    refresh_summary(r, NA_K_SPECS, POLICY)
    assert (item_of(r, "K").judgement, item_of(r, "K").converted_value) == (J.PASS, 3)
    assert r.lot_recommendation == L.APPROVE


def test_na_k_refresh_is_idempotent():
    r = run(na_k("40"), specs=NA_K_SPECS)
    before = r.model_dump()
    refresh_summary(r, NA_K_SPECS, POLICY)
    refresh_summary(r, NA_K_SPECS, POLICY)
    assert r.model_dump() == before


def test_refresh_restores_missing_when_sum_becomes_unusable():
    r = run(na_k("40"), specs=NA_K_SPECS)
    idx = next(n for n, i in enumerate(r.items) if i.normalized_name == "Na+K")
    r.items[idx] = r.items[idx].model_copy(update={"reason_code": R.LOW_CONFIDENCE, "judgement": J.CHECK})
    refresh_summary(r, NA_K_SPECS, POLICY)
    assert (item_of(r, "Na").reason_code, item_of(r, "K").reason_code) == (R.MISSING_REQUIRED, R.MISSING_REQUIRED)


def test_na_k_and_heavy_metal_rules_together():
    r = run(na_k("8"), row("중금속 총량", "2"), specs=[NA, K, PB, TOTAL])
    assert [item_of(r, n).judgement for n in ("Na", "K", "Pb")] == [J.PASS, J.PASS, J.PASS]
    assert r.lot_recommendation == L.APPROVE


def test_heavy_metal_total_spec_copied_without_spec_entry_not_used():
    """규격에 총량 항목이 없을 때도 결과 칸 = 규격 문구인 총량은 쓰지 않는다 (중금속·합산 공통)."""
    total = row("중금속 총량", "≤ 3").model_copy(update={"raw_spec": "≤ 3"})
    assert pb_of(run(total, specs=[NA, PB])).judgement == J.MISSING
