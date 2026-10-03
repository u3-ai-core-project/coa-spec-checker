"""[담당: 장수민] 값 해석 규칙 테스트 — 명세 2.2 표 1행 = 테스트 1개, 이후는 실제 CoA 표기 변형."""
import pytest

from app.core.enums import ValueQualifier as Q
from app.services.judgement.value_parser import is_spec_text_as_result, parse_value


# ---- 명세 2.2 표 -----------------------------------------------------------
def test_spec_exact():
    p = parse_value("3.32")
    assert (p.qualifier, p.value, p.error) == (Q.EXACT, 3.32, None)


def test_spec_less_than():
    p = parse_value("< 20")
    assert (p.qualifier, p.value) == (Q.LESS_THAN, 20)


@pytest.mark.parametrize("raw", ["=<5", "≤ 5", "<=5", "≦5"])
def test_spec_less_equal(raw):
    p = parse_value(raw)
    assert (p.qualifier, p.value) == (Q.LESS_EQUAL, 5)


@pytest.mark.parametrize("raw", ["none detected", "ND", "검출 안 됨", "N.D.", "Not Detected", "불검출"])
def test_spec_not_detected(raw):
    p = parse_value(raw)
    assert (p.qualifier, p.value, p.detection_limit, p.error) == (Q.NOT_DETECTED, None, None, None)


def test_spec_percent_to_ppm():
    p = parse_value("0.002 %", target_unit="ppm")
    assert (p.qualifier, p.value) == (Q.EXACT, 20)


def test_spec_text():
    p = parse_value("White, Crystalline powder")
    assert (p.qualifier, p.value) == (Q.TEXT, "White, Crystalline powder")


def test_spec_oxide_to_element():
    # Na2O 100 ppm → Na 74.19 ppm (계수 0.7419)
    p = parse_value("100", unit="ppm", target_unit="ppm", raw_name="Na₂O")
    assert p.value == pytest.approx(74.19)


def test_spec_unparsable_is_error():
    p = parse_value("3.2-3.4")
    assert p.qualifier is None and p.value is None and p.error


# ---- 실제 CoA 표기 변형 -----------------------------------------------------
def test_unit_inside_value_with_less_equal():
    # 조사 문서 예시 "=<1000 ppm" — 사내 단위가 % 면 0.1
    p = parse_value("=<1000 ppm", target_unit="%")
    assert (p.qualifier, p.value) == (Q.LESS_EQUAL, 0.1)


def test_unit_from_item_field():
    p = parse_value("0.05", unit="%", target_unit="ppm")
    assert p.value == 500


def test_same_unit_no_conversion():
    p = parse_value("0.12", unit="%", target_unit="%")
    assert p.value == 0.12


def test_mg_per_kg_equals_ppm():
    assert parse_value("15 mg/kg", target_unit="ppm").value == 15


def test_wt_percent():
    assert parse_value("99.6 wt%", target_unit="%").value == 99.6


def test_thousands_comma():
    assert parse_value("1,000", unit="ppm", target_unit="ppm").value == 1000


def test_decimal_comma():
    assert parse_value("0,5").value == 0.5


def test_scientific_notation():
    assert parse_value("1.5E-3").value == 0.0015


def test_full_width_less_than():
    assert parse_value("＜10").qualifier == Q.LESS_THAN


def test_not_detected_with_detection_limit():
    p = parse_value("ND (<0.5 ppm)", target_unit="ppm")
    assert (p.qualifier, p.detection_limit) == (Q.NOT_DETECTED, 0.5)


def test_not_detected_detection_limit_converted():
    p = parse_value("N.D.(DL 0.0001%)", target_unit="ppm")
    assert p.detection_limit == 1


def test_greater_than_is_error():
    # 명세 2.2 에 하한 표기(>) 규칙이 없어 해석 실패로 둔다
    p = parse_value("> 99.5")
    assert p.qualifier is None and p.error


def test_unknown_unit_conversion_is_error():
    p = parse_value("3", unit="um", target_unit="ppm")
    assert p.qualifier is None and "단위" in p.error


def test_empty_value_is_error():
    assert parse_value(None).error and parse_value("  ").error


def test_oxide_not_applied_to_sulfate():
    # "Sulfur compounds (as SO4)" 는 환산 계수 표에 없으므로 그대로
    assert parse_value("50", raw_name="Sulfur compounds (as SO4)").value == 50


# ---- 결과 칸 = 규격 문구 ----------------------------------------------------
@pytest.mark.parametrize(
    "raw_value, raw_spec, expected",
    [
        ("≤ 0.01%", "=<0.01 %", True),
        ("<= 20 ppm", "≤20ppm", True),
        ("0.008", "≤ 0.01", False),
        ("ND", None, False),
        (None, "≤ 0.01", False),
    ],
)
def test_spec_text_as_result(raw_value, raw_spec, expected):
    assert is_spec_text_as_result(raw_value, raw_spec) is expected
