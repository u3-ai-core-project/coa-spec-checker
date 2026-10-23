"""[담당: 장수민] follow-ups API 테스트 (명세 v1.4안 4.22). 실제 DB 필요.

후속 조치 목록, 보류 후속 조치 추천, 문의 초안, 같은 공급사 열린 요청 묶음, AI 생성기 실패 시 템플릿 대체.
"""
import json
import sys

import pytest

from app.core.config import settings
from app.core.enums import DocumentStatus, SpecType
from app.models import Document, SpecItem, SpecSet
from app.services import followup_service

PDF = b"%PDF-1.7\n" + b"0" * 50


def row(name, raw_value, conf=0.95):
    return {"raw_name": name, "normalized_name": name, "mapping_source": "dictionary",
            "raw_value": raw_value, "unit": "ppm", "confidence": conf}


MOCKS = {  # 실제 CoA 아님. 규격: Na ≤ 50, Fe ≤ 5, Mg ≤ 10 ppm
    "lot1": {"supplier": "알파 리튬", "lot_no": "L-001",
             "items": [row("Na", "80"), row("Fe", "none detected"), row("Mg", "3", conf=0.5)]},
    "lot2": {"supplier": "알파 리튬 ", "lot_no": "L-002",   # 공급사명 뒤 공백·대소문자 차이는 같은 공급사로
             "items": [row("Na", "10"), row("Fe", "< 20"), row("Mg", "2")]},
    "clean": {"supplier": "알파 리튬", "lot_no": "L-003",
              "items": [row("Na", "10"), row("Fe", "1"), row("Mg", "2")]},
    "other": {"supplier": "베타 케미칼", "lot_no": "B-001",
              "items": [row("Na", "10"), row("Fe", "none detected"), row("Mg", "2")]},
    "lowconf_only": {"supplier": "알파 리튬", "lot_no": "L-004",
                     "items": [row("Na", "10", conf=0.5), row("Fe", "1"), row("Mg", "2")]},
}


@pytest.fixture
def upload(auth_client, db, tmp_path, monkeypatch):
    spec_set = SpecSet(code="T", material_code="LI2CO3", material_name="탄산리튬", is_default=True)
    spec_set.items = [SpecItem(item_name=n, unit="ppm", usl=u, spec_type=SpecType.QUANTITATIVE)
                      for n, u in (("Na", 50), ("Fe", 5), ("Mg", 10))]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    for name, data in MOCKS.items():
        (mock_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _upload(kind: str) -> str:
        r = auth_client.post("/api/v1/documents", files={"file": (f"{kind}.pdf", PDF)},
                             data={"material_code": "LI2CO3"})
        return r.json()["data"]["document_id"]
    return _upload


def follow_ups(client, doc_id):
    r = client.get(f"/api/v1/documents/{doc_id}/follow-ups")
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---- 목록과 추천 ------------------------------------------------------------
def test_lines_split_supplier_and_internal(auth_client, upload):
    d = follow_ups(auth_client, upload("lot1"))
    assert [(ln["target"], ln["code"]) for ln in d["supplier_lines"]] == [("Na", "OUT_OF_SPEC"), ("Fe", "ND_NO_LOD")]
    assert [(ln["target"], ln["code"]) for ln in d["internal_lines"]] == [("Mg", "LOW_CONFIDENCE")]
    fe = d["supplier_lines"][1]
    assert (fe["raw_value"], fe["condition"], fe["to_supplier"]) == ("none detected", "검출한계 ≤ 5 ppm (또는 정량값)", True)


@pytest.mark.parametrize("kind, expected", [
    ("lot1", "request_detection_limit"),   # 부적합 + 검출한계 미기재 → 보류한다면 검출한계 요청
    ("lot2", "request_actual_value"),      # "< 20" 상한값 → 실측값 요청
    ("lowconf_only", "other"),             # 내부 확인만 있음
    ("clean", None),                       # 후속 조치 없음
])
def test_suggested_follow_up(auth_client, upload, kind, expected):
    assert follow_ups(auth_client, upload(kind))["suggested_follow_up"] == expected


def test_clean_document_has_no_draft(auth_client, upload):
    d = follow_ups(auth_client, upload("clean"))
    assert d["supplier_lines"] == [] and d["internal_lines"] == [] and d["draft"] is None


# ---- 문의 초안 --------------------------------------------------------------
def test_single_lot_draft(auth_client, upload):
    draft = follow_ups(auth_client, upload("lot1"))["draft"]
    assert draft["source"] == "template" and draft["lot_nos"] == ["L-001"]
    assert draft["subject"] == "[CoA 확인 요청] 탄산리튬 / Lot L-001"
    assert draft["body"].startswith("알파 리튬 품질 담당자님께,")
    assert 'Na (CoA 기재: "80")' in draft["body"] and "Mg" not in draft["body"]   # 내부 확인 항목 제외


def test_same_supplier_open_requests_combined(auth_client, upload):
    first = upload("lot1")
    upload("lot2")
    upload("clean")      # 요청 없음 → 묶음에서 제외
    upload("other")      # 다른 공급사 → 제외
    d = follow_ups(auth_client, first)
    assert [(o["lot_no"], o["request_count"]) for o in d["open_documents"]] == [("L-001", 2), ("L-002", 1)]
    combined = d["combined_draft"]
    assert combined["lot_nos"] == ["L-001", "L-002"]
    assert combined["subject"] == "[CoA 확인 요청] 탄산리튬 2개 로트 (L-001, L-002)"
    assert "[Lot L-001]" in combined["body"] and "[Lot L-002]" in combined["body"]
    assert combined["body"].count("감사합니다.") == 1   # 메일 1통


def test_closed_documents_not_combined(auth_client, upload, db):
    first = upload("lot1")
    second = upload("lot2")
    doc = db.get(Document, second)
    doc.status = DocumentStatus.APPROVED
    db.commit()
    d = follow_ups(auth_client, first)
    assert [o["lot_no"] for o in d["open_documents"]] == ["L-001"] and d["combined_draft"] is None


def test_draft_follows_review_progress(auth_client, upload):
    doc_id = upload("lot1")
    items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    fe = next(i for i in items if i["normalized_name"] == "Fe")
    auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{fe['item_id']}",
                      json={"detection_limit": 1, "value_source": "supplier_reply", "reason": "공급사 회신 (LOD 1 ppm)"})
    d = follow_ups(auth_client, doc_id)
    assert [ln["target"] for ln in d["supplier_lines"]] == ["Na"]   # 회신으로 해결된 Fe 는 빠짐


# ---- 초안 생성기 (AI 연결 자리) ----------------------------------------------------
class BrokenAIDrafter:
    source = "ai"

    def draft(self, supplier, lots):
        raise RuntimeError("LLM timeout")


class FakeAIDrafter:
    source = "ai"

    def draft(self, supplier, lots):
        return "AI 제목", f"{supplier}: {sum(len(lot.lines) for lot in lots)}건"


def test_ai_drafter_used_when_configured(auth_client, upload, monkeypatch):
    monkeypatch.setattr(followup_service, "get_drafter", lambda: FakeAIDrafter())
    draft = follow_ups(auth_client, upload("lot1"))["draft"]
    assert (draft["source"], draft["subject"], draft["body"]) == ("ai", "AI 제목", "알파 리튬: 2건")


def test_ai_failure_falls_back_to_template(auth_client, upload, monkeypatch):
    monkeypatch.setattr(followup_service, "get_drafter", lambda: BrokenAIDrafter())
    draft = follow_ups(auth_client, upload("lot1"))["draft"]
    assert draft["source"] == "template_fallback" and draft["subject"].startswith("[CoA 확인 요청]")


def test_ai_package_missing_falls_back_to_template(auth_client, upload, monkeypatch):
    # INQUIRY_DRAFTER=ai 인데 ai 패키지(coa_ai)가 없으면 생성기 준비가 실패한다 → 500 이 아니라 템플릿
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "ai")
    monkeypatch.setitem(sys.modules, "coa_ai", None)                    # import coa_ai 가 실패하게
    monkeypatch.delitem(sys.modules, "app.pipeline.ai_drafter", raising=False)  # 이미 읽힌 어댑터를 쓰지 않게
    monkeypatch.delitem(sys.modules, "app.pipeline.llm_client", raising=False)
    doc_id = upload("lot1")
    draft = follow_ups(auth_client, doc_id)["draft"]
    assert draft["source"] == "template_fallback" and draft["subject"].startswith("[CoA 확인 요청]")


# ---- 오류 -------------------------------------------------------------------
def test_not_found(auth_client, upload):
    r = auth_client.get("/api/v1/documents/nope/follow-ups")
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_not_ready(auth_client, upload, db):
    doc_id = upload("lot1")
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.QUEUED
    db.commit()
    r = auth_client.get(f"/api/v1/documents/{doc_id}/follow-ups")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_READY"
