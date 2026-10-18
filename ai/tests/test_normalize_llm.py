"""항목명 정규화의 LLM 제안 단계: 규칙이 못 찾은 것만 묻고, 제안은 항상 확인 필요(ai, 0.6)."""
import pytest

from coa_ai.normalize import AI_CAP, NONE, Mapping, Normalizer
from tests.fake_llm import FakeLLM


def test_rule_hits_do_not_ask_llm():
    llm = FakeLLM({"name": "K"})
    assert Normalizer("LI2CO3", llm=llm).map("Sodium (Na)") == Mapping("Na", "dictionary", 1.0)
    assert llm.calls == []


def test_llm_suggestion_is_ai_with_cap():
    llm = FakeLLM({"name": "Na"})
    assert Normalizer("LI2CO3", llm=llm).map("Natrium content") == Mapping("Na", "ai", AI_CAP)
    assert len(llm.calls) == 1


def test_llm_none_answer_keeps_raw():
    assert Normalizer("LI2CO3", llm=FakeLLM({"name": NONE})).map("Lot Size") == Mapping("Lot Size", "ai", AI_CAP)


def test_llm_unavailable_keeps_raw():
    assert Normalizer("LI2CO3", llm=FakeLLM(None)).map("Lot Size") == Mapping("Lot Size", "ai", AI_CAP)


def test_answer_outside_candidates_keeps_raw():
    llm = FakeLLM({"name": "LiOH 함량"})  # 탄산리튬 후보에는 없음
    assert Normalizer("LI2CO3", llm=llm).map("Hydroxide assay") == Mapping("Hydroxide assay", "ai", AI_CAP)


@pytest.mark.parametrize("raw", ["Ti", "Co", "As"])
def test_element_symbol_not_asked(raw):
    llm = FakeLLM({"name": "Na"})
    assert Normalizer("LI2CO3", llm=llm).map(raw) == Mapping(raw, "ai", AI_CAP)
    assert llm.calls == []


@pytest.mark.parametrize("raw", ["Ti⁴⁺", "Co2+"])
def test_charged_element_symbol_not_asked(raw):
    llm = FakeLLM({"name": "Na"})
    assert Normalizer("LI2CO3", llm=llm).map(raw).name == raw
    assert llm.calls == []


def test_candidates_are_per_material():
    lioh = dict(Normalizer("LIOH").candidates())
    li2co3 = dict(Normalizer("LI2CO3").candidates())
    assert "LiOH 함량" in lioh and "순도" not in lioh
    assert "순도" in li2co3 and "LiOH 함량" not in li2co3
    assert {"염화물", "중금속 총량", "Na", "Pb"} <= set(li2co3)
    assert all(meaning for meaning in li2co3.values())
    assert li2co3["Na"] == "나트륨 원소"


def test_prompt_has_material_and_enum():
    llm = FakeLLM({"name": NONE})
    n = Normalizer("LI2CO3", llm=llm)
    n.map("Natrium content")
    call = llm.calls[0]
    assert call["schema"]["properties"]["name"]["enum"] == [name for name, _ in n.candidates()] + [NONE]
    assert "원자재: 탄산리튬" in call["user"]
    assert "Natrium content" in call["user"]
    assert "중금속 총량" in call["system"]
