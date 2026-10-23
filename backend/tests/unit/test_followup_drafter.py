"""[담당: 장수민] 문의 초안 생성기 선택과 템플릿 대체 (명세 v1.4안 4.22). DB 불필요.

followup_service._draft() 를 직접 불러, 생성기 준비·생성이 실패해도 템플릿 초안으로 대신하는지 본다.
ai 패키지(coa_ai)가 설치돼 있어도 없는 것처럼 만들어 시험하므로 어느 환경에서나 돈다.
"""
import sys

import pytest

from app.core.config import settings
from app.core.enums import ReasonCode as R
from app.services import followup_service
from app.services.inquiry_draft import FollowUpLine, LotRequest, TemplateDrafter

LOTS = [LotRequest("L-001", "탄산리튬", [
    FollowUpLine(target="Fe", code=R.ND_NO_LOD.value, label="검출 안 됨, 검출한계 미기재", why="검출한계 미기재",
                 condition="검출한계 ≤ 5 ppm (또는 정량값)", raw_value="none detected", to_supplier=True),
])]


@pytest.fixture
def no_ai_package(monkeypatch):
    """coa_ai 를 import 할 수 없는 상태 (설치 안 된 환경과 같게)."""
    monkeypatch.setitem(sys.modules, "coa_ai", None)
    monkeypatch.delitem(sys.modules, "app.pipeline.ai_drafter", raising=False)
    monkeypatch.delitem(sys.modules, "app.pipeline.llm_client", raising=False)


def test_template_setting_uses_template(monkeypatch):
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "template")
    out = followup_service._draft("알파 리튬", LOTS)
    assert out.source == "template" and out.subject.startswith("[CoA 확인 요청]") and out.lot_nos == ["L-001"]


def test_ai_package_missing_falls_back_to_template(monkeypatch, no_ai_package):
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "ai")
    with pytest.raises(ImportError):
        followup_service.get_drafter()          # 생성기 준비 단계에서 실패하는 상황이 맞는지
    out = followup_service._draft("알파 리튬", LOTS)
    assert out.source == "template_fallback" and "Fe" in out.body


def test_unknown_setting_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "nope")
    out = followup_service._draft("알파 리튬", LOTS)
    assert out.source == "template_fallback"


def test_template_failure_is_raised(monkeypatch):
    # 템플릿이 실패하면 대신할 것이 없으므로 그대로 올린다 (API 는 500)
    def broken(self, supplier, lots):
        raise RuntimeError("template bug")
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "template")
    monkeypatch.setattr(TemplateDrafter, "draft", broken)
    with pytest.raises(RuntimeError, match="template bug"):
        followup_service._draft("알파 리튬", LOTS)
