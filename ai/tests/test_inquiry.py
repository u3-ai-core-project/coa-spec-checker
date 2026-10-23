"""공급사 문의 초안: LLM 글을 코드가 검사하고, 걸리면 InquiryDraftError (백엔드가 템플릿으로 대체)."""
import pytest

from coa_ai.inquiry import InquiryDraftError, check_draft, draft_inquiry
from tests.fake_llm import FakeLLM

ND_LOTS = [{"lot_no": "A0475173", "material_name": "탄산리튬", "requests": [
    {"target": "Fe", "label": "검출 안 됨, 검출한계 미기재",
     "why": "검출 안 됨으로 적혔지만 검출한계가 없어 사내 상한 5 ppm 충족 여부를 알 수 없음",
     "request": "검출한계 ≤ 5 ppm (또는 정량값)", "raw_value": "N.D."}]}]

TWO_LOTS = [
    {"lot_no": "A0468916", "material_name": "탄산리튬", "requests": [
        {"target": "Ca", "label": "결과 칸에 규격 문구 기재", "why": "결과 칸에 규격 문구(=<100 ppm)가 그대로 적힘",
         "request": "실측값이 기재된 CoA 재발행", "raw_value": "=<100 ppm"}]},
    {"lot_no": "A0474013", "material_name": "탄산리튬", "requests": [
        {"target": "황산염", "label": "보고 상한이 사내 상한보다 큼",
         "why": "보고값 < 0.2 % 가 사내 상한 0.05 % 보다 커서 충족 여부를 알 수 없음",
         "request": "정량값 또는 상한값 ≤ 0.05 % 보고", "raw_value": "< 0.2 %"}]},
]

GOOD_ND = """제목: [CoA 확인 요청] 탄산리튬 Lot A0475173

Thermo Fisher Scientific 품질 담당자님께,

송부하신 탄산리튬(Lot A0475173) 시험성적서를 검토하던 중 아래 항목의 확인을 요청드립니다.

1. Fe (CoA 기재: "N.D.")
   - 사유: 검출한계가 없어 사내 상한 5 ppm 충족 여부를 알 수 없습니다.
   - 요청: 검출한계 ≤ 5 ppm 또는 정량값을 알려 주십시오.

확인 후 회신 부탁드립니다.

[담당자 이름]"""


def draft(text, lots=ND_LOTS, supplier="Thermo Fisher Scientific"):
    return draft_inquiry(supplier, lots, FakeLLM(text_answer=text))


def test_good_draft_passes():
    subject, body = draft(GOOD_ND)
    assert subject == "[CoA 확인 요청] 탄산리튬 Lot A0475173"
    assert body.startswith("Thermo Fisher Scientific 품질 담당자님께")


def test_prompt_carries_requests_as_json():
    llm = FakeLLM(text_answer=GOOD_ND)
    draft_inquiry("Thermo Fisher Scientific", ND_LOTS, llm)
    user = llm.calls[0]["user"]
    assert '"request": "검출한계 ≤ 5 ppm (또는 정량값)"' in user
    assert '"supplier": "Thermo Fisher Scientific"' in user


def test_invented_number_rejected():
    with pytest.raises(InquiryDraftError, match="7"):
        draft(GOOD_ND.replace("확인 후 회신", "7일 이내에 확인 후 회신"))


def test_missing_target_rejected():
    with pytest.raises(InquiryDraftError, match="Fe"):
        draft(GOOD_ND.replace("1. Fe (CoA", "1. 철 (CoA"))


def test_missing_request_number_rejected():
    text = GOOD_ND.replace("사내 상한 5 ppm", "사내 상한").replace("검출한계 ≤ 5 ppm 또는", "검출한계 또는")
    with pytest.raises(InquiryDraftError, match="5"):
        draft(text)


def test_missing_lot_rejected():
    with pytest.raises(InquiryDraftError, match="A0475173"):
        draft(GOOD_ND.replace("A0475173", "해당 로트"))


def test_table_rejected():
    with pytest.raises(InquiryDraftError, match="표"):
        draft(GOOD_ND + "\n| 항목 | 값 |")


def test_disposition_rejected():
    with pytest.raises(InquiryDraftError, match="반품"):
        draft(GOOD_ND.replace("확인 후 회신 부탁드립니다.", "확인되지 않으면 반품하겠습니다."))


def test_no_subject_line_rejected():
    with pytest.raises(InquiryDraftError, match="제목"):
        draft(GOOD_ND.split("\n", 2)[2])


def test_no_llm_raises():
    with pytest.raises(InquiryDraftError):
        draft_inquiry("x", ND_LOTS, None)
    with pytest.raises(InquiryDraftError):
        draft(None)


def test_missing_lot_no_and_supplier():
    lots = [{**ND_LOTS[0], "lot_no": None}]
    text = GOOD_ND.replace("Lot A0475173", "로트").replace("Thermo Fisher Scientific", "공급사")
    subject, _ = draft(text, lots=lots, supplier=None)
    assert subject == "[CoA 확인 요청] 탄산리튬 로트"


def test_lot_count_is_allowed_number():
    text = """제목: [CoA 확인 요청] 탄산리튬 2개 로트

Acros Organics 품질 담당자님께, 2개 로트의 확인을 요청드립니다.

[Lot A0468916]
1. Ca (CoA 기재: "=<100 ppm") - 요청: 실측값이 기재된 CoA 재발행

[Lot A0474013]
1. 황산염 (CoA 기재: "< 0.2 %") - 요청: 정량값 또는 상한값 ≤ 0.05 % 보고

[담당자 이름]"""
    assert check_draft(*draft(text, lots=TWO_LOTS, supplier="Acros Organics"), "Acros Organics", TWO_LOTS) == []
