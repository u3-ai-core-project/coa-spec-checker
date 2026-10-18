"""추출값 자체 검증: 틀렸을 가능성이 높은 항목에 이유를 붙인다 (판정은 하지 않음)."""
import pytest

from coa_ai.models import Item
from coa_ai.selfcheck import SELF_CHECK_CAP, check_items


def item(name, value, spec=None, normalized=None, source="dictionary", confidence=0.95, page=1):
    return Item(raw_name=name, normalized_name=normalized or name, mapping_source=source, raw_value=value,
                raw_spec=spec, unit=None, confidence=confidence, bbox={"page": page, "x": 0, "y": 0, "w": 0, "h": 0})


def reasons(*items):
    items = list(items)
    check_items(items)
    return [i.check_reasons for i in items]


@pytest.mark.parametrize("value", ["40.0 ppm 0|", "50.0 ppm 0l", "2000 ppm 0|σ", "1O ppm"])
def test_ocr_junk_in_value(value):
    (r,) = reasons(item("Pb", value, "40.0 ppm 이하"))
    assert len(r) == 1 and "스캔 잡음" in r[0]


@pytest.mark.parametrize("value", ["100.5 % (Li2CO3)", "< 0.10 ppm", "White", "ND (<0.5 ppm)", "0.0018", "Conforms"])
def test_clean_values_pass(value):
    assert reasons(item("x", value, "≤ 5 ppm")) == [[]]


def test_duplicate_numeric_item_with_different_values():
    r = reasons(item("Sodium (Na)", "12 ppm", normalized="Na"), item("Na", "15 ppm", normalized="Na"))
    assert all(len(x) == 1 and "두 번" in x[0] for x in r)


def test_duplicate_qualitative_items_are_fine():
    # Fisher 양식 B: 'Appearance (Color)' 와 'Appearance (Form)' 은 둘 다 외관이다
    assert reasons(item("Appearance (Color)", "White", "White", normalized="외관"),
                   item("Appearance (Form)", "Crystalline powder", "Crystalline powder", normalized="외관")) == [[], []]


def test_duplicate_same_value_is_fine():
    assert reasons(item("Na", "12 ppm"), item("Na", "12 ppm")) == [[], []]


def test_ai_mapped_duplicates_are_not_checked():
    assert reasons(item("x", "1", normalized="Ag", source="ai"), item("y", "2", normalized="Ag", source="ai")) == [[], []]


def test_unit_kind_conflict():
    (r,) = reasons(item("Particle size D50", "8.5 µm", "≤ 50 ppm"))
    assert len(r) == 1 and "단위" in r[0]


def test_same_unit_kind_is_fine():
    assert reasons(item("Na", "0.0012 %", "≤ 50 ppm")) == [[]]


def test_swapped_value_and_spec():
    (r,) = reasons(item("LiOH", "56.5 – 57.5", "56.99"))
    assert len(r) == 1 and "바뀌었" in r[0]


def test_value_far_over_limit():
    (r,) = reasons(item("Carbonate", "36 %", "≤ 0.40 %"))
    assert len(r) == 1 and "50배" in r[0]


def test_real_fail_is_not_flagged():
    assert reasons(item("Carbonate", "0.36 %", "≤ 0.35 %"), item("Fe", "15 ppm", "≤ 5 ppm")) == [[], []]


def test_flagged_item_confidence_is_capped():
    a, b = item("Pb", "40.0 ppm 0|"), item("Na", "12 ppm")
    check_items([a, b])
    assert (a.confidence, b.confidence) == (SELF_CHECK_CAP, 0.95)
    assert SELF_CHECK_CAP < 0.8  # 서버 LOW_CONFIDENCE_THRESHOLD 미만 → 확인 필요


def test_lower_confidence_is_kept():
    a = item("Pb", "40.0 ppm 0|", confidence=0.6)
    check_items([a])
    assert a.confidence == 0.6


def test_duplicates_on_different_pages_are_fine():
    # 여러 쪽에 걸친 성적서(로트별 쪽, 이어지는 표)는 같은 항목이 쪽마다 나올 수 있다
    assert reasons(item("Na", "12 ppm", page=1), item("Na", "15 ppm", page=2)) == [[], []]


def test_reason_quotes_whole_junk_token():
    (r,) = reasons(item("Pb", "2000 ppm 0|σ"))
    assert r == ["값에 스캔 잡음으로 보이는 글자가 있음('0|σ')"]
