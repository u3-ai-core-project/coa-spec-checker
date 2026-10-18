"""[담당: 고도영] AI 문의 초안 생성기 어댑터와 LLM 클라이언트 설정 (DB 불필요). ai/ 패키지가 없으면 건너뛴다."""
import pytest

coa_ai = pytest.importorskip("coa_ai")

from app.core.config import settings  # noqa: E402
from app.core.enums import ReasonCode as R  # noqa: E402
from app.pipeline import llm_client  # noqa: E402
from app.pipeline.ai_drafter import AIDrafter  # noqa: E402
from app.services import followup_service  # noqa: E402
from app.services.inquiry_draft import FollowUpLine, LotRequest  # noqa: E402


def line(target, code, condition, raw_value="x"):
    return FollowUpLine(target=target, code=code.value, label="짧은 이름", why="근거", condition=condition,
                        raw_value=raw_value, to_supplier=True)


def test_ai_drafter_uses_supplier_request_text():
    lots = AIDrafter.to_inquiry_lots([LotRequest("L-1", "탄산리튬", [
        line("Mg", R.MISSING_REQUIRED, "별도 성적서 값 또는 자체 시험값 입력", None),
        line("Fe", R.ND_NO_LOD, "검출한계 ≤ 5 ppm (또는 정량값)"),
    ])])
    assert (lots[0]["lot_no"], lots[0]["material_name"]) == ("L-1", "탄산리튬")
    mg, fe = lots[0]["requests"]
    assert mg["request"] == "해당 항목의 시험 결과(별도 성적서) 송부"   # 담당자용 해결 조건 대신 공급사용 문구
    assert fe["request"] == "검출한계 ≤ 5 ppm (또는 정량값)"
    assert set(mg) == {"target", "label", "why", "request", "raw_value"}


def test_get_drafter_ai(monkeypatch):
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "ai")
    assert isinstance(followup_service.get_drafter(), AIDrafter)


def test_draft_without_llm_raises(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BASE_URL", None)
    with pytest.raises(coa_ai.InquiryDraftError, match="LLM_BASE_URL"):
        AIDrafter().draft("알파 리튬", [LotRequest("L-1", "탄산리튬", [line("Fe", R.ND_NO_LOD, "검출한계 ≤ 5 ppm")])])


def test_get_llm_is_shared_per_url(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BASE_URL", None)
    assert llm_client.get_llm() is None
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://127.0.0.1:9")
    client = llm_client.get_llm()
    assert isinstance(client, coa_ai.LLMClient) and client is llm_client.get_llm()
