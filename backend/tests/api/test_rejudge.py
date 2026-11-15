"""[담당: 장수민] 규격 세트를 바꿔 다시 판정 API 테스트 (POST /documents/{id}/rejudge, 멘토님 피드백: 검수 화면 규격 드롭다운).
실제 DB 필요.

  - 미리보기(apply=false): 문서·이력이 바뀌지 않고, 처분 완료 문서도 볼 수 있다
  - 적용(apply=true): 규격 세트가 바뀌고 respec 이력이 남는다. 사유 필수, 처분 전 문서만
  - 다시 판정 규칙: 담당자가 입력한 값 유지, 누락 항목 재생성, 규격 버전 불일치 재계산, 다른 문서 오류는 유지
저장소의 실제 시드(seeds/data)를 적재해서 쓴다.
"""
import io
import json

import pytest
from openpyxl import load_workbook

from app.core.config import settings
from app.core.enums import DocumentStatus
from app.models import Document
from seeds.seed_specs import seed_specs

PDF = b"%PDF-1.7\n" + b"0" * 50


def row(name, raw_value, unit="ppm"):
    return {"raw_name": name, "normalized_name": name, "mapping_source": "dictionary",
            "raw_value": raw_value, "unit": unit, "confidence": 0.95}


# 실제 CoA 아님. D1 필수 항목을 모두 갖추고 Na 만 80 ppm: D1(≤ 50) 부적합, 완화(≤ 100) 적합, 엄격(≤ 30) 부적합
FULL_NA80 = {"supplier": "알파 리튬", "lot_no": "L-080", "items": [
    row("순도", "99.7", "%"), row("Na", "80"), row("K", "5"), row("Fe", "2"), row("Ca", "10"), row("Mg", "5"),
    row("Pb", "1"), row("염화물", "10"), row("황산염", "300"), row("자성이물", "20", "ppb"),
]}
# Mg·자성이물이 없는 문서: D1 이면 누락(보류), DEMO-R 이면 승인 권고
FISHER_LIKE = {"supplier": "Fisher", "lot_no": "A0396981", "items": [
    row("순도", "99.6", "%"), row("Na", "30"), row("K", "5"), row("Fe", "2"), row("Ca", "10"),
    row("염화물", "10"), row("황산염", "200"), row("중금속 총량", "2"),
]}
# 모든 항목이 D1 안이고 CoA 가 2023판 규격을 적용: D1(2023)은 문제 없고 2013판 세트로 보면 버전 불일치
FULL_OK_2023 = {**FULL_NA80, "lot_no": "L-023", "applied_standard": "YS/T 582-2023",
                "items": [row("Na", "40") if i["normalized_name"] == "Na" else i for i in FULL_NA80["items"]]}
FULL_OK_2013 = {**FULL_OK_2023, "lot_no": "L-013", "applied_standard": "YS/T 582-2013"}


@pytest.fixture
def make_doc(auth_client, db, tmp_path, monkeypatch):
    seed_specs(db)
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    mocks = {"full": FULL_NA80, "fisher": FISHER_LIKE, "ok2023": FULL_OK_2023, "ok2013": FULL_OK_2013}
    for name, data in mocks.items():
        (mock_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _make(kind="full", spec_set_code=None, received_lot_no=None) -> str:
        data = {"material_code": "LI2CO3"}
        if spec_set_code:
            data["spec_set_code"] = spec_set_code
        if received_lot_no:
            data["received_lot_no"] = received_lot_no
        r = auth_client.post("/api/v1/documents", files={"file": (f"{kind}.pdf", PDF)}, data=data)
        assert r.status_code == 201, r.text
        return r.json()["data"]["document_id"]
    return _make


def rejudge(client, doc_id, spec_set_code, apply=False, reason=None, **extra):
    body = {"spec_set_code": spec_set_code, "apply": apply, "reason": reason, **extra}
    return client.post(f"/api/v1/documents/{doc_id}/rejudge", json=body)


def extraction(client, doc_id) -> dict:
    return client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]


def by_name(result) -> dict:
    return {i["normalized_name"]: i for i in result["items"]}


def detail(client, doc_id) -> dict:
    return client.get(f"/api/v1/documents/{doc_id}").json()["data"]


def logs(client, doc_id) -> list[dict]:
    return client.get(f"/api/v1/documents/{doc_id}/review-logs").json()["data"]


def error_code(r) -> str:
    return r.json()["error"]["code"]


# ---- 미리보기 (apply=false) --------------------------------------------------
def test_preview_shows_other_result_without_changing_document(auth_client, make_doc):
    doc_id = make_doc("full")                                         # 기본 세트 D1: Na 80 부적합
    before = extraction(auth_client, doc_id)
    assert before["lot_recommendation"] == "reject"

    r = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["applied"] is False
    assert (data["spec_set"]["code"], data["spec_set"]["grade"]) == ("LI2CO3-D1-RELAXED", "D1-완화")
    assert data["previous_spec_set"]["code"] == "LI2CO3-D1-2023"
    assert (data["lot_recommendation_before"], data["lot_recommendation_after"]) == ("reject", "approve")
    assert data["summary_before"]["fail"] == 1 and data["summary_after"]["fail"] == 0
    assert data["changed_items"] == [{"item_name": "Na", "before": "fail", "after": "pass"}]
    assert by_name(data["result"])["Na"]["judgement"] == "pass"       # GET /extraction 과 같은 형식의 전체 결과

    # 문서·이력은 그대로
    assert extraction(auth_client, doc_id) == before
    d = detail(auth_client, doc_id)
    assert (d["spec_set_code"], d["status"], d["lot_recommendation"]) == ("LI2CO3-D1-2023", "extracted", "reject")
    assert logs(auth_client, doc_id) == []


def test_preview_can_go_back_and_forth(auth_client, make_doc):
    """드롭다운을 왔다 갔다 해도 매번 저장된 결과를 기준으로 계산한다 (미리보기끼리 영향을 주지 않는다)."""
    doc_id = make_doc("full")
    relaxed = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED").json()["data"]
    strict = rejudge(auth_client, doc_id, "LI2CO3-D1-STRICT").json()["data"]
    again = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED").json()["data"]
    assert relaxed["lot_recommendation_after"] == "approve" and strict["lot_recommendation_after"] == "reject"
    assert again["result"] == relaxed["result"]
    assert strict["changed_items"] == []                              # D1 도 엄격도 Na 부적합이라 달라진 항목 없음


def test_preview_allowed_on_approved_document(auth_client, make_doc):
    doc_id = make_doc("full")
    r = auth_client.post(f"/api/v1/documents/{doc_id}/approve",
                         json={"decision": "reject", "reason": None})
    assert r.status_code == 200, r.text
    r = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED")
    assert r.status_code == 200 and r.json()["data"]["lot_recommendation_after"] == "approve"
    assert detail(auth_client, doc_id)["status"] == "approved"


def test_same_spec_set_is_noop(auth_client, make_doc):
    doc_id = make_doc("full")
    r = rejudge(auth_client, doc_id, "LI2CO3-D1-2023", apply=True, reason="같은 세트")
    data = r.json()["data"]
    assert r.status_code == 200 and data["applied"] is False and data["changed_items"] == []
    assert data["lot_recommendation_before"] == data["lot_recommendation_after"] == "reject"
    assert logs(auth_client, doc_id) == [] and detail(auth_client, doc_id)["status"] == "extracted"


# ---- 적용 (apply=true) -------------------------------------------------------
def test_apply_changes_spec_set_and_leaves_respec_log(auth_client, make_doc):
    doc_id = make_doc("full")
    r = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="D1 이 너무 빡빡해 완화 기준으로 확인")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["applied"] is True and data["lot_recommendation_after"] == "approve"

    d = detail(auth_client, doc_id)
    assert (d["spec_set_code"], d["spec_grade"], d["lot_recommendation"]) == ("LI2CO3-D1-RELAXED", "D1-완화", "approve")
    assert d["status"] == "in_review"                                 # 값 수정과 같은 규칙: 검수가 시작된 것으로 본다
    saved = extraction(auth_client, doc_id)
    assert saved["lot_recommendation"] == "approve" and saved["review_status"] == "in_review"
    assert by_name(saved)["Na"]["judgement"] == "pass"

    [log] = logs(auth_client, doc_id)
    assert (log["item_id"], log["action"]) == ("document", "respec")
    assert (log["before_value"], log["after_value"]) == ("LI2CO3-D1-2023", "LI2CO3-D1-RELAXED")
    assert log["reason"] == "D1 이 너무 빡빡해 완화 기준으로 확인" and log["reviewer_name"] == "김사용"


def test_apply_requires_reason_and_changes_nothing(auth_client, make_doc):
    doc_id = make_doc("full")
    for reason in (None, "", "   "):
        r = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason=reason)
        assert r.status_code == 400 and error_code(r) == "REASON_REQUIRED"
    assert detail(auth_client, doc_id)["spec_set_code"] == "LI2CO3-D1-2023"
    assert logs(auth_client, doc_id) == []


def test_preview_does_not_need_reason(auth_client, make_doc):
    assert rejudge(auth_client, make_doc("full"), "LI2CO3-D1-STRICT").status_code == 200


def test_apply_rejected_on_approved_document(auth_client, make_doc):
    doc_id = make_doc("full")
    assert auth_client.post(f"/api/v1/documents/{doc_id}/approve",
                            json={"decision": "reject", "reason": None}).status_code == 200
    r = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="사후 변경")
    assert r.status_code == 409 and error_code(r) == "ALREADY_APPROVED"
    assert detail(auth_client, doc_id)["spec_set_code"] == "LI2CO3-D1-2023"


def test_apply_on_hold_document_moves_to_in_review(auth_client, make_doc):
    doc_id = make_doc("fisher")                                       # D1: Mg·자성이물 누락 → 보류 권고
    assert auth_client.post(f"/api/v1/documents/{doc_id}/hold",
                            json={"follow_up": "request_actual_value", "reason": "누락 확인"}).status_code == 200
    assert detail(auth_client, doc_id)["status"] == "on_hold"
    assert rejudge(auth_client, doc_id, "LI2CO3-DEMO-R", apply=True, reason="실물 CoA 기준").status_code == 200
    assert detail(auth_client, doc_id)["status"] == "in_review"


@pytest.mark.parametrize("status", [DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.FAILED])
@pytest.mark.parametrize("apply", [False, True])
def test_not_ready_documents(auth_client, make_doc, db, status, apply):
    doc_id = make_doc("full")
    db.query(Document).filter(Document.id == doc_id).update({"status": status})
    db.commit()
    r = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=apply, reason="x")
    assert r.status_code == 409 and error_code(r) == "NOT_READY"


# ---- 입력 검사 ---------------------------------------------------------------
def test_document_not_found(auth_client, make_doc):
    r = rejudge(auth_client, "nope", "LI2CO3-D1-RELAXED")
    assert r.status_code == 404 and error_code(r) == "DOCUMENT_NOT_FOUND"


@pytest.mark.parametrize("code", ["LI2CO3-NOPE", "LIOH-BG-V1"])      # 없는 세트, 다른 원자재의 세트
def test_unknown_spec_set(auth_client, make_doc, code):
    doc_id = make_doc("full")
    r = rejudge(auth_client, doc_id, code, apply=True, reason="x")
    assert r.status_code == 400 and error_code(r) == "UNKNOWN_SPEC_SET"
    assert detail(auth_client, doc_id)["spec_set_code"] == "LI2CO3-D1-2023"


def test_blank_spec_set_code_is_not_default_set(auth_client, make_doc):
    """공백만 보내면 기본 세트로 조용히 대체하지 않고 오류로 돌려준다."""
    doc_id = make_doc("full", "LI2CO3-D1-RELAXED")
    r = rejudge(auth_client, doc_id, "   ")
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"
    assert rejudge(auth_client, doc_id, "").status_code == 400
    assert auth_client.post(f"/api/v1/documents/{doc_id}/rejudge", json={}).status_code == 400


def test_requires_login(client):
    assert client.post("/api/v1/documents/x/rejudge", json={"spec_set_code": "A"}).status_code == 401


# ---- 다시 판정 규칙 ----------------------------------------------------------
def test_reviewer_input_is_kept_after_apply(auth_client, make_doc):
    """담당자가 입력한 값(출처·검수 표시 포함)은 규격 세트를 바꿔도 유지되고 새 한도로 다시 판정된다."""
    doc_id = make_doc("full")
    na = by_name(extraction(auth_client, doc_id))["Na"]
    r = auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{na['item_id']}",
                          json={"converted_value": 90, "reason": "원본 확인"})
    assert r.status_code == 200, r.text
    assert rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="완화 기준").status_code == 200
    kept = by_name(extraction(auth_client, doc_id))["Na"]
    assert (kept["converted_value"], kept["reviewed"], kept["value_source"]) == (90, True, "correction")
    assert kept["judgement"] == "pass" and kept["spec_usl"] == 100    # 90 ≤ 100
    # 엄격 기준으로 다시 바꾸면 같은 입력값이 부적합이 된다
    assert rejudge(auth_client, doc_id, "LI2CO3-D1-STRICT", apply=True, reason="엄격 기준").status_code == 200
    kept = by_name(extraction(auth_client, doc_id))["Na"]
    assert (kept["converted_value"], kept["judgement"], kept["spec_usl"]) == (90, "fail", 30)
    assert [(x["action"], x["after_value"]) for x in logs(auth_client, doc_id)] == [
        ("edit", "90 ppm"), ("respec", "LI2CO3-D1-RELAXED"), ("respec", "LI2CO3-D1-STRICT")]


def test_missing_items_follow_new_set(auth_client, make_doc):
    """필수 항목이 다른 세트로 바꾸면 누락 항목이 사라지고, 되돌리면 다시 생긴다."""
    doc_id = make_doc("fisher")
    d1 = extraction(auth_client, doc_id)
    assert {n for n, i in by_name(d1).items() if i["judgement"] == "missing"} == {"Mg", "자성이물"}
    assert d1["lot_recommendation"] == "hold"

    preview = rejudge(auth_client, doc_id, "LI2CO3-DEMO-R").json()["data"]
    assert preview["lot_recommendation_after"] == "approve" and preview["summary_after"]["missing"] == 0
    assert {c["item_name"]: (c["before"], c["after"]) for c in preview["changed_items"]} == {
        "Mg": ("missing", None), "자성이물": ("missing", None)}

    assert rejudge(auth_client, doc_id, "LI2CO3-DEMO-R", apply=True, reason="실물 CoA").status_code == 200
    assert extraction(auth_client, doc_id)["summary"]["missing"] == 0
    back = rejudge(auth_client, doc_id, "LI2CO3-D1-2023", apply=True, reason="되돌림").json()["data"]
    assert back["lot_recommendation_after"] == "hold" and back["summary_after"]["missing"] == 2
    assert {n for n, i in by_name(extraction(auth_client, doc_id)).items() if i["judgement"] == "missing"} == {"Mg", "자성이물"}


def issue_codes(result) -> list[str]:
    return [i["code"] for i in result["document_issues"]]


def test_spec_version_mismatch_is_recomputed(auth_client, make_doc):
    """CoA 2023판 규격: D1(2023)과는 맞고 2013판 세트로 바꾸면 규격 버전 불일치(보류 권고)가 생긴다."""
    doc_id = make_doc("ok2023")
    base = extraction(auth_client, doc_id)
    assert issue_codes(base) == [] and base["lot_recommendation"] == "approve"

    preview = rejudge(auth_client, doc_id, "LI2CO3-2013").json()["data"]
    assert issue_codes(preview["result"]) == ["SPEC_VERSION_MISMATCH"]
    assert (preview["lot_recommendation_before"], preview["lot_recommendation_after"]) == ("approve", "hold")
    assert issue_codes(extraction(auth_client, doc_id)) == []         # 미리보기는 저장하지 않는다

    assert rejudge(auth_client, doc_id, "LI2CO3-2013", apply=True, reason="구판 비교").status_code == 200
    assert issue_codes(extraction(auth_client, doc_id)) == ["SPEC_VERSION_MISMATCH"]
    # 같은 2023판 세트(완화)로 바꾸면 불일치가 사라진다
    back = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="2023판 기준").json()["data"]
    assert issue_codes(back["result"]) == [] and back["lot_recommendation_after"] == "approve"


def test_spec_version_mismatch_resolved_by_matching_set(auth_client, make_doc):
    """처음부터 맞지 않던 세트(2013판 CoA × D1)는 맞는 세트로 바꾸면 불일치가 해소된다."""
    doc_id = make_doc("ok2013")
    assert issue_codes(extraction(auth_client, doc_id)) == ["SPEC_VERSION_MISMATCH"]
    data = rejudge(auth_client, doc_id, "LI2CO3-2013", apply=True, reason="2013판 기준").json()["data"]
    assert issue_codes(data["result"]) == [] and data["lot_recommendation_after"] == "approve"


def test_other_document_issues_are_kept(auth_client, make_doc):
    """입고 로트 ≠ CoA 로트 같은 규격 세트와 무관한 문서 오류는 세트를 바꿔도 남는다."""
    doc_id = make_doc("ok2023", received_lot_no="ZZZ-1")
    assert issue_codes(extraction(auth_client, doc_id)) == ["LOT_MISMATCH"]
    data = rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="완화 기준").json()["data"]
    assert issue_codes(data["result"]) == ["LOT_MISMATCH"] and data["lot_recommendation_after"] == "hold"


# ---- 이후 흐름: 리포트·후속 조치·규격 수정 ------------------------------------
def test_report_shows_respec_history(auth_client, make_doc):
    doc_id = make_doc("full")
    assert rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="완화 기준").status_code == 200
    r = auth_client.get(f"/api/v1/documents/{doc_id}/report")
    assert r.status_code == 200
    cells = {str(c.value) for ws in load_workbook(io.BytesIO(r.content)).worksheets
             for row_ in ws.iter_rows() for c in row_ if c.value is not None}
    assert {"규격 세트 변경", "(문서 전체)", "LI2CO3-D1-2023", "LI2CO3-D1-RELAXED"} <= cells
    assert any("LI2CO3-D1-RELAXED" in c and "D1-완화" in c for c in cells)   # 리포트 상단 '사내 규격' 칸도 바뀐 세트


def test_later_review_uses_new_spec_set(auth_client, make_doc):
    """적용 뒤 값 수정·확인은 바뀐 세트를 기준으로 판정한다 (옛 세트로 되돌아가지 않는다)."""
    doc_id = make_doc("full")
    assert rejudge(auth_client, doc_id, "LI2CO3-D1-STRICT", apply=True, reason="엄격 기준").status_code == 200
    k = by_name(extraction(auth_client, doc_id))["K"]
    r = auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{k['item_id']}",
                          json={"converted_value": 9, "reason": "원본 확인"})
    assert r.status_code == 200 and r.json()["data"]["item"]["judgement"] == "fail"   # 9 > 엄격 상한 8 (D1 이면 적합)


def test_spec_edit_rejudge_follows_documents_new_set(auth_client, make_doc, admin):
    """규격 항목 수정(rejudge=true)은 문서가 지금 쓰는 세트의 문서만 다시 판정한다."""
    doc_id = make_doc("full")
    assert rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="완화 기준").status_code == 200
    specs = auth_client.get("/api/v1/specs", params={"spec_set_code": "LI2CO3-D1-RELAXED"}).json()["data"]
    na = next(s for s in specs if s["item_name"] == "Na")
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na['id']}", json={"usl": 60, "reason": "완화 기준 조정", "rejudge": True})
    assert r.status_code == 200 and [d["document_id"] for d in r.json()["data"]["rejudged_documents"]] == [doc_id]
    assert by_name(extraction(auth_client, doc_id))["Na"]["judgement"] == "fail"        # 80 > 60
