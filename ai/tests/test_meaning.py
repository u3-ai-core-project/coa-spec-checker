"""결과 칸 의미 분류: 규칙 표 + 코드 비교, 규칙이 못 읽은 열린 문장만 LLM."""
import pytest

from coa_ai.meaning import Condition, ValueMeaning, classify, parse_condition
from tests.fake_llm import FakeLLM

# 모델 테스트(ai/bench/llm/cases.py VALUE_SYNTHETIC)의 변형 24개: (결과 칸, 규격 칸, 정답)
SYNTHETIC = [
    ("≤100 ppm", "100 ppm max", "spec_copy"),
    ("Max 20 ppm", "≤ 20 ppm", "spec_copy"),
    ("0.35 % max", "≤ 0.35 %", "spec_copy"),
    ("NMT 20 ppm", "≤20 ppm", "spec_copy"),
    ("20 ppm 이하", "≤ 20 ppm", "spec_copy"),
    ("≤0.0020", "不大于0.0020", "spec_copy"),
    ("=<0.002 %", "=<0.2 %", "bound"),
    ("< 10 ppm", "≤ 20 ppm", "bound"),
    ("Less than 1 ppm", "≤ 5 ppm", "bound"),
    ("10 ppm 미만", "20 ppm 이하", "bound"),
    ("BDL", "≤ 10 ppm", "nd"),
    ("< LOD", "≤ 5 ppm", "nd"),
    ("未检出", "≤0.0010", "nd"),
    ("ND (<0.5 ppm)", "≤ 5 ppm", "nd"),
    ("Below detection limit", "≤ 5 ppm", "nd"),
    ("Conforms to specification", "White powder", "pass_text"),
    ("Meets ACS specifications", "≤ 5 ppm", "pass_text"),
    ("As per specification", "White crystalline powder", "pass_text"),
    ("合格", "白色粉末", "pass_text"),
    ("적합", "백색 분말", "pass_text"),
    ("White, free-flowing powder", "White powder", "description"),
    ("白色结晶粉末", "白色结晶粉末，无可见杂质", "description"),
    ("99.62 % (dry basis)", "≥ 99.5 %", "number"),
    ("8.5 µm", "3 – 20 µm", "number"),
]


@pytest.mark.parametrize("value, spec, kind", SYNTHETIC)
def test_synthetic_cases(value, spec, kind):
    m = classify(value, spec)
    assert m.kind == kind
    assert m.reason and not m.reason.startswith("AI 판단")


def test_same_text_without_digits_is_not_spec_copy():
    assert classify("White powder", "White powder").kind == "description"


def test_same_text_with_digits_is_spec_copy():
    m = classify("=<1000 ppm", "=<1000 ppm")
    assert m.kind == "spec_copy"
    assert "규격" in m.reason


def test_range_copy():
    assert classify("56.5-57.5 %", "56.5 – 57.5 %").kind == "spec_copy"


def test_different_unit_is_not_copy():
    assert classify("≤ 20 ppm", "≤ 20 %").kind == "bound"


def test_fullwidth_and_comma_numbers():
    assert classify("＜0,5 ppm", "≤ 5 ppm").kind == "bound"
    assert classify("1,000 ppm max", "≤ 1000 ppm").kind == "spec_copy"


def test_bound_reason_mentions_spec_condition():
    m = classify("< 10 ppm", "≤ 20 ppm")
    assert "< 10 ppm" in m.reason and "<= 20 ppm" in m.reason


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_value(value):
    assert classify(value, "≤ 5 ppm") == ValueMeaning(None, None)


def test_unreadable_value_without_llm_is_none():
    m = classify("approx. 12 ppm (ICP)", "≤ 20 ppm")
    assert m.kind is None and m.reason


def test_llm_decides_open_text():
    llm = FakeLLM({"kind": "pass_text", "reason": "합격을 뜻함"})
    m = classify("Satisfactory", "White powder", llm)
    assert m.kind == "pass_text"
    assert m.reason.startswith("AI 판단: ")
    assert llm.calls[0]["schema"]["properties"]["kind"]["enum"] == ["pass_text", "description"]


def test_llm_not_asked_when_rules_decide():
    llm = FakeLLM({"kind": "description", "number": "", "reason": "x"})
    for value, spec, _ in SYNTHETIC[:20]:  # 규칙 표·합격 문구 표로 정해지는 것
        classify(value, spec, llm)
    assert llm.calls == []


def test_llm_number_must_appear_in_text():
    wrong = FakeLLM({"kind": "number", "number": "13", "reason": "숫자"})
    assert classify("approx. 12 ppm (ICP)", "≤ 20 ppm", wrong).kind is None
    right = FakeLLM({"kind": "number", "number": "12", "reason": "숫자"})
    assert classify("approx. 12 ppm (ICP)", "≤ 20 ppm", right).kind == "number"


def test_llm_bound_needs_operator_word():
    llm = FakeLLM({"kind": "bound", "number": "12", "reason": "부등호"})
    assert classify("12 ppm (ICP) typical", "≤ 20 ppm", llm).kind is None


def test_llm_never_makes_spec_copy():
    llm = FakeLLM({"kind": "number", "number": "12", "reason": "x"})
    classify("approx. 12 ppm (ICP)", "≤ 20 ppm", llm)
    assert "spec_copy" not in llm.calls[0]["schema"]["properties"]["kind"]["enum"]


def test_llm_answer_outside_kinds_is_ignored():
    llm = FakeLLM({"kind": "spec_copy", "number": "12", "reason": "x"})
    assert classify("approx. 12 ppm (ICP)", "≤ 20 ppm", llm).kind is None


def test_llm_prompt_has_name_value_and_spec():
    llm = FakeLLM(None)
    classify("Satisfactory", "White powder", llm, raw_name="Appearance")
    user = llm.calls[0]["user"]
    assert "Appearance" in user and "Satisfactory" in user and "White powder" in user


def test_parse_condition():
    assert parse_condition("0.35 % max") == Condition("value", "<=", 0.35, "%", None)
    assert parse_condition("NLT 99.5%") == Condition("value", ">=", 99.5, "%", None)
    assert parse_condition("56.5～57.5") == Condition("range", None, 56.5, None, 57.5)
    assert parse_condition("N.D.") == Condition("nd", None, None, None, None)
    assert parse_condition("12 ppm") == Condition("value", "=", 12.0, "ppm", None)
    assert parse_condition("approx. 12 ppm (ICP)") is None
