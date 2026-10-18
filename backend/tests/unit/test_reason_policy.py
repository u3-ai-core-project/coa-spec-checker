"""[담당: 장수민] 사유코드·해결 조건·판정 정책 테스트 (명세 v1.4안).

- 기존 판정 분기마다 사유코드와 해결 조건이 붙는지
- 정책(사유코드별 판정, 검출한계 경계, 미등록 항목명)을 바꾸면 판정이 바뀌는지
- 잘못된 정책 설정은 거부하는지
"""
import pytest

from app.core.config import Settings
from app.core.enums import Judgement as J, MappingSource, ReasonCode as R, ResolutionType as T, ValueQualifier as Q
from app.schemas.extraction import ExtractedItem
from app.services.judgement.item_judge import evaluate_item
from app.services.judgement.missing_items import build_missing_items
from app.services.judgement.policy import DEFAULT_REASON_JUDGEMENT, JudgementPolicy, UnmappedPolicy
from app.services.judgement.spec_rule import SpecRule
from app.services.judgement.value_parser import ParsedValue

POLICY = JudgementPolicy()  # 기본값 = API 명세 기준
NA = SpecRule("Na", unit="ppm", usl=50)
FE = SpecRule("Fe", unit="ppm", usl=5)
PURITY = SpecRule("순도", unit="%", lsl=99.5)


def item(raw_value, name="Na", conf=0.95, raw_spec=None, unit=None, raw_name=None, source=MappingSource.AI):
    return ExtractedItem(item_id="item-001", raw_name=raw_name or name, normalized_name=name, mapping_source=source,
                         raw_value=raw_value, raw_spec=raw_spec, unit=unit, confidence=conf)


def judge(raw_value, spec, policy=POLICY, **kw):
    override = kw.pop("override", None)
    reviewed = kw.pop("reviewed", False)
    return evaluate_item(item(raw_value, name=spec.item_name if spec else "기타", **kw), spec,
                         policy=policy, override=override, reviewed=reviewed)


# ---- 판정 분기 → 사유코드·판정·해결 조건 종류 (기본 정책) ----------------------
@pytest.mark.parametrize("raw, spec, kw, judgement, code, rtype", [
    ("30", NA, {"unit": "ppm"}, J.PASS, None, None),
    ("80", NA, {"unit": "ppm"}, J.FAIL, R.OUT_OF_SPEC, T.CONFIRM),
    ("< 20", NA, {"unit": "ppm"}, J.PASS, None, None),
    ("< 100", NA, {"unit": "ppm"}, J.UNDETERMINED, R.BOUND_ABOVE_LIMIT, T.ACTUAL_VALUE),
    ("none detected", FE, {}, J.CHECK, R.ND_NO_LOD, T.DETECTION_LIMIT),
    ("ND (<20 ppm)", FE, {}, J.UNDETERMINED, R.LOD_ABOVE_LIMIT, T.DETECTION_LIMIT),
    ("=<1000", NA, {"raw_spec": "≤ 1000"}, J.UNDETERMINED, R.SPEC_COPIED, T.ACTUAL_VALUE),
    ("30", NA, {"unit": "ppm", "conf": 0.5}, J.CHECK, R.LOW_CONFIDENCE, T.CONFIRM),
    ("3.2-3.4", NA, {}, J.CHECK, R.UNPARSEABLE_VALUE, T.CONFIRM),
    ("< 99.9", PURITY, {"unit": "%"}, J.UNDETERMINED, R.LOWER_LIMIT_UNVERIFIABLE, T.ACTUAL_VALUE),
], ids=["pass", "out-of-spec", "bound-pass", "bound-above", "nd-no-lod", "lod-above", "spec-copied",
        "low-confidence", "unparseable", "lower-limit"])
def test_reason_code_per_branch(raw, spec, kw, judgement, code, rtype):
    r = judge(raw, spec, **kw)
    assert (r.judgement, r.reason_code) == (judgement, code)
    assert (r.resolution.type if r.resolution else None) == rtype


def test_pass_item_has_no_reason_or_resolution():
    r = judge("12", NA, unit="ppm")
    assert r.reason_code is None and r.resolution is None


def test_missing_item_reason_and_resolution():
    missing = ExtractedItem(item_id="spec-001", normalized_name="Mg", mapping_source=MappingSource.SPEC)
    r = evaluate_item(missing, SpecRule("Mg", unit="ppm", usl=10), policy=POLICY)
    assert (r.judgement, r.reason_code, r.resolution.type) == (J.MISSING, R.MISSING_REQUIRED, T.INTERNAL_TEST)


def test_converted_oos_from_oxide():
    # Na2O 0.04 % → 400 ppm × 0.7419 ≈ 296.8 ppm > 50 (기획안 v2 7.2 U24E051 사례)
    r = judge("0.04 %", NA, raw_name="Na2O")
    assert (r.judgement, r.reason_code) == (J.FAIL, R.CONVERTED_OOS)
    assert r.converted_value == pytest.approx(296.76)
    assert "Na2O" in r.judgement_reason and "Na2O" in r.resolution.condition


def test_oxide_within_spec_is_plain_pass():
    r = judge("0.001 %", NA, raw_name="Na2O")   # 10 ppm × 0.7419 ≈ 7.4 ppm
    assert (r.judgement, r.reason_code) == (J.PASS, None)


# ---- 해결 조건 수치 ---------------------------------------------------------
def test_resolution_numbers_for_nd_no_lod():
    res = judge("none detected", FE).resolution
    assert (res.operator, res.threshold, res.unit, res.target_item) == ("<=", 5, "ppm", "Fe")
    assert res.condition == "검출한계 ≤ 5 ppm (또는 정량값)"


def test_resolution_numbers_for_bound_above_limit():
    res = judge("< 20", FE, unit="ppm").resolution
    assert (res.operator, res.threshold) == ("<=", 5)


# ---- 회신값 입력 → 자동 재판정 ------------------------------------------------
def test_detection_limit_reply_resolves_nd():
    # Fe "none detected" → 공급사 회신 "검출한계 2 ppm" 입력
    r = judge("none detected", FE, override=ParsedValue(Q.NOT_DETECTED, None, detection_limit=2))
    assert (r.judgement, r.reason_code, r.resolution) == (J.PASS, None, None)


def test_reply_that_does_not_meet_condition_stays_exception():
    r = judge("none detected", FE, override=ParsedValue(Q.NOT_DETECTED, None, detection_limit=10))
    assert (r.judgement, r.reason_code) == (J.UNDETERMINED, R.LOD_ABOVE_LIMIT)


def test_actual_value_reply_resolves_bound():
    r = judge("< 20", FE, unit="ppm", override=ParsedValue(Q.EXACT, 3))
    assert (r.judgement, r.reason_code) == (J.PASS, None)


# ---- 정책: 사유코드별 판정 (안건 2) -------------------------------------------
def test_policy_spec_copied_as_check():
    policy = POLICY.with_overrides(reason_judgement={**DEFAULT_REASON_JUDGEMENT, R.SPEC_COPIED: J.CHECK})
    r = judge("=<1000", NA, policy=policy, raw_spec="≤ 1000")
    assert (r.judgement, r.reason_code) == (J.CHECK, R.SPEC_COPIED)


def test_policy_from_settings_overrides():
    s = Settings(REASON_JUDGEMENT={"SPEC_COPIED": "check", "AMBIGUOUS_ANALYTE": "undetermined"})
    p = JudgementPolicy.from_settings(s)
    assert p.judgement_for(R.SPEC_COPIED) == J.CHECK
    assert p.judgement_for(R.AMBIGUOUS_ANALYTE) == J.UNDETERMINED
    assert p.judgement_for(R.BOUND_ABOVE_LIMIT) == J.UNDETERMINED  # 지정하지 않은 코드는 기본값


@pytest.mark.parametrize("overrides", [
    {"OUT_OF_SPEC": "check"},          # 고정 코드
    {"MISSING_REQUIRED": "check"},     # 고정 코드
    {"SPEC_COPIED": "fail"},           # 고를 수 없는 판정
    {"NOT_A_CODE": "check"},           # 없는 코드
    {"SPEC_COPIED": "maybe"},          # 없는 판정
])
def test_policy_rejects_invalid_overrides(overrides):
    with pytest.raises(ValueError):
        JudgementPolicy.from_settings(Settings(REASON_JUDGEMENT=overrides))


def test_every_reason_code_has_judgement_and_resolution():
    for code in R:
        assert POLICY.judgement_for(code) in J
        # 해결 조건 문구가 정의되지 않은 코드가 없어야 한다
        from app.services.judgement.resolutions import build_resolution
        assert build_resolution(code, item_name="Na", spec=NA).condition


# ---- 정책: 검출한계 경계 -----------------------------------------------------
def test_nd_limit_equal_to_usl_inclusive_pass():
    assert judge("ND (<5 ppm)", FE).judgement == J.PASS


def test_nd_limit_equal_to_usl_exclusive_undetermined():
    policy = POLICY.with_overrides(nd_limit_inclusive=False)
    r = judge("ND (<5 ppm)", FE, policy=policy)
    assert (r.judgement, r.reason_code) == (J.UNDETERMINED, R.LOD_ABOVE_LIMIT)
    assert r.resolution.operator == "<" and r.resolution.condition.startswith("검출한계 <")


# ---- 정책: 미등록 AI 항목명 (안건 3) ------------------------------------------
def test_unmapped_ai_item_reference_by_default():
    r = judge("1.2", None)
    assert (r.judgement, r.reason_code, r.judgement_reason) == (J.PASS, None, "규격 없음")


def test_unmapped_ai_item_check_policy():
    policy = POLICY.with_overrides(unmapped_ai_item=UnmappedPolicy.CHECK)
    r = judge("1.2", None, policy=policy)
    assert (r.judgement, r.reason_code) == (J.CHECK, R.UNMAPPED_ITEM)


def test_unmapped_dictionary_item_stays_reference_under_check_policy():
    # 사전으로 매핑했는데 규격에 없는 항목(B, D10 등)은 원래 참고 항목
    policy = POLICY.with_overrides(unmapped_ai_item=UnmappedPolicy.CHECK)
    r = judge("1.2", None, policy=policy, source=MappingSource.DICTIONARY)
    assert (r.judgement, r.reason_code) == (J.PASS, None)


# ---- 필수 여부 (is_required) -------------------------------------------------
def test_optional_spec_item_is_not_missing():
    specs = [SpecRule("Na", "ppm", usl=50), SpecRule("Mg", "ppm", usl=10, is_required=False)]
    missing = build_missing_items([item("10")], specs)
    assert [m.normalized_name for m in missing] == []
