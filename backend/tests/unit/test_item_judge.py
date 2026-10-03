"""[담당: 장수민] 항목 판정 규칙 테스트 — 명세 2.3 표 1행 = 테스트 1개, 이후는 재판정 규칙."""
import pytest

from app.core.enums import Judgement as J, MappingSource, SpecType, ValueQualifier as Q
from app.schemas.extraction import ExtractedItem
from app.services.judgement.item_judge import evaluate_item
from app.services.judgement.spec_rule import SpecRule
from app.services.judgement.value_parser import ParsedValue

TH = 0.8
NA = SpecRule("Na", unit="ppm", lsl=None, usl=25)          # 상한만 있는 불순물
PURITY = SpecRule("순도", unit="%", lsl=99.5, usl=None)     # 하한만 있는 순도
MOISTURE = SpecRule("수분", unit="%", lsl=0.0, usl=0.4)     # 양쪽 다 있는 항목
APPEARANCE = SpecRule("외관", unit=None, lsl=None, usl=None, spec_type=SpecType.QUALITATIVE)


def item(raw_value, name="Na", conf=0.95, raw_spec=None, unit=None, raw_name=None, source=MappingSource.AI):
    return ExtractedItem(
        item_id="item-001", raw_name=raw_name or name, normalized_name=name, mapping_source=source,
        raw_value=raw_value, raw_spec=raw_spec, unit=unit, confidence=conf,
    )


def judge(raw_value, spec, **kw):
    reviewed = kw.pop("reviewed", False)
    override = kw.pop("override", None)
    return evaluate_item(item(raw_value, name=spec.item_name if spec else "기타", **kw), spec,
                         threshold=TH, reviewed=reviewed, override=override)


# ---- 명세 2.3 표 -----------------------------------------------------------
def test_exact_in_range_pass():
    r = judge("12", NA, unit="ppm")
    assert (r.judgement, r.deviation) == (J.PASS, None)
    assert (r.value_qualifier, r.converted_value, r.spec_usl) == (Q.EXACT, 12, 25)


def test_exact_out_of_range_fail_with_deviation():
    r = judge("30", NA, unit="ppm")
    assert (r.judgement, r.deviation) == (J.FAIL, 5)
    assert "상한" in r.judgement_reason


def test_less_than_within_usl_pass():
    r = judge("< 20", NA, unit="ppm")
    assert r.judgement == J.PASS


def test_less_than_above_usl_undetermined():
    r = judge("< 100", NA, unit="ppm")
    assert r.judgement == J.UNDETERMINED
    assert r.judgement_reason == "상한값만 기재됨(< 100 ppm), 사내 상한 25 ppm보다 큼"


def test_not_detected_with_limit_below_usl_pass():
    r = judge("ND (<0.5 ppm)", NA)
    assert (r.judgement, r.detection_limit) == (J.PASS, 0.5)


def test_not_detected_without_limit_check():
    r = judge("none detected", NA)
    assert (r.judgement, r.judgement_reason) == (J.CHECK, "검출한계 미기재")


def test_result_equals_spec_text_undetermined():
    r = judge("≤ 25 ppm", NA, raw_spec="=<25ppm")
    assert (r.judgement, r.judgement_reason) == (J.UNDETERMINED, "결과 칸이 규격 문구와 같음")


def test_missing_item_from_spec():
    missing = ExtractedItem(item_id="spec-001", normalized_name="Na", mapping_source=MappingSource.SPEC)
    r = evaluate_item(missing, NA, threshold=TH)
    assert r.judgement == J.MISSING and r.bbox is None and r.converted_value is None


def test_low_confidence_check_overrides_value():
    r = judge("30", NA, unit="ppm", conf=0.62)   # 값만 보면 fail
    assert r.judgement == J.CHECK
    assert r.judgement_reason == "추출 신뢰도 낮음(0.62)"
    assert r.converted_value == 30               # 화면 표시용 값은 채운다


def test_no_spec_reference():
    r = judge("1.2", None)
    assert (r.judgement, r.judgement_reason) == (J.PASS, "규격 없음")


def test_qualitative_reference():
    r = judge("White, Crystalline powder", APPEARANCE)
    assert (r.judgement, r.value_qualifier) == (J.PASS, Q.TEXT)
    assert r.judgement_reason == "정성 항목, 판정 제외"


# ---- 경계값, 하한 ----------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [("25", J.PASS), ("25.0001", J.FAIL), ("0", J.PASS)])
def test_usl_boundary_inclusive(raw, expected):
    assert judge(raw, NA, unit="ppm").judgement == expected


def test_below_lsl_fail_negative_deviation():
    r = judge("99.3", PURITY, unit="%")
    assert r.judgement == J.FAIL and r.deviation == pytest.approx(-0.2)
    assert "하한" in r.judgement_reason


def test_less_than_on_item_with_lsl_undetermined():
    # 수분처럼 하한도 있으면 "< x" 만으로는 하한 충족을 알 수 없다
    assert judge("< 0.1", MOISTURE, unit="%").judgement == J.UNDETERMINED


def test_not_detected_limit_above_usl_undetermined():
    assert judge("ND (<50 ppm)", NA).judgement == J.UNDETERMINED


def test_unparsable_value_check():
    r = judge("3.2-3.4", NA)
    assert r.judgement == J.CHECK and r.converted_value is None


def test_text_on_quantitative_item_check():
    assert judge("Conforms", NA).judgement == J.CHECK


def test_percent_value_against_ppm_spec():
    # 0.002 % = 20 ppm ≤ 25 ppm
    r = judge("0.002 %", NA)
    assert (r.judgement, r.converted_value) == (J.PASS, 20)


# ---- 재판정 (명세 2.3 아래 규칙, 4.9, 4.10) -------------------------------
def test_confirm_removes_confidence_condition():
    r = judge("30", NA, unit="ppm", conf=0.62, reviewed=True)
    assert r.judgement == J.FAIL


def test_confirm_keeps_check_when_detection_limit_missing():
    r = judge("ND", NA, conf=0.5, reviewed=True)
    assert (r.judgement, r.judgement_reason) == (J.CHECK, "검출한계 미기재")


def test_edit_undetermined_with_actual_value():
    r = judge("< 100", NA, override=ParsedValue(Q.EXACT, 8))
    assert (r.judgement, r.converted_value) == (J.PASS, 8)


def test_edit_missing_item_with_internal_test_value():
    missing = ExtractedItem(item_id="spec-001", normalized_name="Na", mapping_source=MappingSource.SPEC)
    r = evaluate_item(missing, NA, threshold=TH, override=ParsedValue(Q.EXACT, 40))
    assert (r.judgement, r.deviation, r.mapping_source) == (J.FAIL, 15, MappingSource.SPEC)


def test_edit_skips_spec_text_rule():
    r = judge("≤ 25 ppm", NA, raw_spec="=<25ppm", override=ParsedValue(Q.EXACT, 10))
    assert r.judgement == J.PASS


def test_input_item_is_not_mutated():
    src = item("30", unit="ppm")
    evaluate_item(src, NA, threshold=TH)
    assert not hasattr(src, "judgement")
