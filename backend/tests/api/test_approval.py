"""[담당: 장수민] 처분 API 테스트 (명세 4.12~4.15). 실제 DB 필요.

최종 처분(승인·조건부 승인·불합격), 보류, 처분 취소(ADMIN), 처분 이력, 권한.
"""
import json

import pytest

from app.core.config import settings
from app.core.enums import DocumentStatus, SpecType
from app.core.security import create_access_token
from app.models import Document, SpecItem, SpecSet

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


def row(name, raw_value, conf=0.95, unit="ppm"):
    return {"raw_name": name, "normalized_name": name, "mapping_source": "dictionary",
            "raw_value": raw_value, "unit": unit, "confidence": conf}


# 로트 권고별 목업 추출 결과 (실제 CoA 아님). 규격: Na ≤ 50, Fe ≤ 5 ppm
MOCKS = {
    "approve": [row("Na", "12"), row("Fe", "1")],                    # 승인 권고
    "reject": [row("Na", "80"), row("Fe", "1")],                     # 불합격 권고 (Na 부적합)
    "hold": [row("Na", "12"), row("Fe", "none detected")],           # 보류 권고 (검출한계 미기재)
    "lowconf": [row("Na", "12", conf=0.6), row("Fe", "1")],          # 신뢰도 낮음 미처리
}


@pytest.fixture
def make_doc(auth_client, db, tmp_path, monkeypatch):
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=SpecType.QUANTITATIVE),
                      SpecItem(item_name="Fe", unit="ppm", usl=5, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    for name, items in MOCKS.items():
        (mock_dir / f"{name}.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _make(kind: str) -> str:
        r = auth_client.post("/api/v1/documents", files={"file": (f"{kind}.pdf", PDF)},
                             data={"material_code": "LI2CO3"})
        return r.json()["data"]["document_id"]
    return _make


def approve(client, doc_id, decision, reason=None):
    return client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": decision, "reason": reason})


def hold(client, doc_id, follow_up="request_detection_limit", reason="검출한계 요청"):
    return client.post(f"/api/v1/documents/{doc_id}/hold", json={"follow_up": follow_up, "reason": reason})


def cancel(client, doc_id, reason="처분 오류"):
    return client.post(f"/api/v1/documents/{doc_id}/cancel-approval", json={"reason": reason})


def err(r):
    return r.status_code, r.json()["error"]["code"]


# ---- 최종 처분 (4.12) --------------------------------------------------------
def test_accept_matching_recommendation(auth_client, make_doc, db):
    doc_id = make_doc("approve")
    r = approve(auth_client, doc_id, "accept")
    assert r.status_code == 200
    d = r.json()["data"]
    assert (d["status"], d["lot_recommendation"], d["final_decision"], d["approved_by"]) == \
        ("approved", "approve", "accept", "김사용")
    assert d["approved_at"].endswith("+09:00")

    doc = db.get(Document, doc_id)
    db.refresh(doc)
    assert doc.decision_reason is None and doc.extraction.result["review_status"] == "approved"


def test_reject_matching_recommendation_needs_no_reason(auth_client, make_doc):
    assert approve(auth_client, make_doc("reject"), "reject").json()["data"]["final_decision"] == "reject"


def test_accept_on_reject_recommendation_invalid(auth_client, make_doc):
    assert err(approve(auth_client, make_doc("reject"), "accept", "사유")) == (422, "INVALID_DECISION")


@pytest.mark.parametrize("kind, decision", [
    ("reject", "conditional_accept"),   # 조건부 승인은 항상 사유 필수
    ("approve", "conditional_accept"),
    ("approve", "reject"),              # 권고와 다른 처분
    ("hold", "accept"),                 # 보류 권고에는 같은 처분이 없음
    ("hold", "reject"),
])
def test_reason_required(auth_client, make_doc, kind, decision):
    doc_id = make_doc(kind)
    assert err(approve(auth_client, doc_id, decision)) == (400, "REASON_REQUIRED")
    assert err(approve(auth_client, doc_id, decision, "   ")) == (400, "REASON_REQUIRED")   # 공백만
    r = approve(auth_client, doc_id, decision, "  공급사 재시험 성적 확인  ")
    assert r.status_code == 200


def test_reason_is_saved_trimmed(auth_client, make_doc, db):
    doc_id = make_doc("reject")
    approve(auth_client, doc_id, "conditional_accept", "  Na 초과분 혼합 사용 조건  ")
    doc = db.get(Document, doc_id)
    db.refresh(doc)
    assert doc.decision_reason == "Na 초과분 혼합 사용 조건"


def test_pending_low_confidence_blocks_approve(auth_client, make_doc):
    doc_id = make_doc("lowconf")
    r = approve(auth_client, doc_id, "accept", "사유")
    assert err(r) == (422, "PENDING_LOW_CONFIDENCE_ITEMS") and "Na" in r.json()["error"]["message"]

    # 값 확인 후에는 처분 가능 (확인 후 Na 12 → 적합 → 승인 권고)
    items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    na = next(i for i in items if i["normalized_name"] == "Na")
    auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{na['item_id']}/confirm")
    assert approve(auth_client, doc_id, "accept").status_code == 200


def test_already_approved(auth_client, make_doc):
    doc_id = make_doc("approve")
    approve(auth_client, doc_id, "accept")
    assert err(approve(auth_client, doc_id, "accept")) == (409, "ALREADY_APPROVED")
    assert err(hold(auth_client, doc_id)) == (409, "ALREADY_APPROVED")
    # 처분 후에는 검수(값 수정)도 막힌다
    items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    r = auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{items[0]['item_id']}", json={"converted_value": 1})
    assert err(r) == (409, "ALREADY_APPROVED")


@pytest.mark.parametrize("status", [DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.FAILED])
def test_not_ready(auth_client, make_doc, db, status):
    doc_id = make_doc("approve")
    doc = db.get(Document, doc_id)
    doc.status = status
    db.commit()
    assert err(approve(auth_client, doc_id, "accept")) == (409, "NOT_READY")
    assert err(hold(auth_client, doc_id)) == (409, "NOT_READY")


def test_not_found(auth_client, make_doc):
    assert err(approve(auth_client, "nope", "accept")) == (404, "DOCUMENT_NOT_FOUND")


@pytest.mark.parametrize("body", [{}, {"decision": "maybe"}])
def test_invalid_body(auth_client, make_doc, body):
    r = auth_client.post(f"/api/v1/documents/{make_doc('approve')}/approve", json=body)
    assert err(r) == (400, "VALIDATION_ERROR")


def test_approve_from_on_hold(auth_client, make_doc):
    doc_id = make_doc("hold")
    hold(auth_client, doc_id)
    assert approve(auth_client, doc_id, "reject", "검출한계 회신 없음").status_code == 200


# ---- 보류 (4.13) ------------------------------------------------------------
def test_hold(auth_client, make_doc, db):
    doc_id = make_doc("hold")
    r = hold(auth_client, doc_id)
    assert r.status_code == 200 and r.json()["data"] == {"document_id": doc_id, "status": "on_hold"}
    doc = db.get(Document, doc_id)
    db.refresh(doc)
    assert doc.extraction.result["review_status"] == "on_hold" and doc.final_decision is None


@pytest.mark.parametrize("follow_up", ["request_single_value", "request_reissue", "request_correct_coa"])
def test_hold_with_new_follow_up_values(auth_client, make_doc, follow_up):
    assert hold(auth_client, make_doc("hold"), follow_up=follow_up).status_code == 200


def test_hold_reason_required(auth_client, make_doc):
    assert err(hold(auth_client, make_doc("hold"), reason=" ")) == (400, "REASON_REQUIRED")


def test_hold_invalid_follow_up(auth_client, make_doc):
    assert err(hold(auth_client, make_doc("hold"), follow_up="call_supplier")) == (400, "VALIDATION_ERROR")


def test_hold_twice_records_both(auth_client, make_doc):
    doc_id = make_doc("hold")
    hold(auth_client, doc_id, follow_up="request_detection_limit", reason="1차 요청")
    assert hold(auth_client, doc_id, follow_up="other", reason="2차 독촉").status_code == 200
    logs = auth_client.get(f"/api/v1/documents/{doc_id}/approval-logs").json()["data"]
    assert [log["reason"] for log in logs] == ["1차 요청", "2차 독촉"]


# ---- 처분 취소 (4.14) ---------------------------------------------------------
def test_cancel_by_admin(auth_client, make_doc, admin, db):
    doc_id = make_doc("approve")
    approve(auth_client, doc_id, "accept")
    auth_client.login_as(admin)
    r = cancel(auth_client, doc_id)
    assert r.status_code == 200 and r.json()["data"]["status"] == "in_review"

    doc = db.get(Document, doc_id)
    db.refresh(doc)
    assert (doc.final_decision, doc.decision_reason, doc.approved_by, doc.approved_at) == (None, None, None, None)
    assert doc.extraction.result["review_status"] == "in_review"
    # 취소 후 다시 처분할 수 있다
    assert approve(auth_client, doc_id, "accept").json()["data"]["approved_by"] == "관리자"


def test_cancel_forbidden_for_user(auth_client, make_doc):
    doc_id = make_doc("approve")
    approve(auth_client, doc_id, "accept")
    assert err(cancel(auth_client, doc_id)) == (403, "FORBIDDEN")


def test_cancel_not_approved(auth_client, make_doc, admin):
    doc_id = make_doc("approve")
    auth_client.login_as(admin)
    assert err(cancel(auth_client, doc_id)) == (409, "NOT_APPROVED")


def test_cancel_reason_required(auth_client, make_doc, admin):
    doc_id = make_doc("approve")
    approve(auth_client, doc_id, "accept")
    auth_client.login_as(admin)
    assert err(cancel(auth_client, doc_id, reason="")) == (400, "REASON_REQUIRED")


# ---- 이력 (4.15) -------------------------------------------------------------
def test_approval_logs(auth_client, make_doc, admin):
    doc_id = make_doc("hold")
    hold(auth_client, doc_id, follow_up="request_detection_limit", reason="LOD 요청")
    approve(auth_client, doc_id, "accept", "LOD 회신 확인")
    auth_client.login_as(admin)
    cancel(auth_client, doc_id, reason="회신 문서 오류")
    logs = auth_client.get(f"/api/v1/documents/{doc_id}/approval-logs").json()["data"]
    assert [(log["action"], log["decision"], log["follow_up"], log["user_name"]) for log in logs] == [
        ("hold", None, "request_detection_limit", "김사용"),
        ("approve", "accept", None, "김사용"),
        ("cancel", None, None, "관리자"),
    ]
    assert logs[0]["reason"] == "LOD 요청" and logs[0]["created_at"].endswith("+09:00")


def test_approval_logs_not_found(auth_client, make_doc):
    assert err(auth_client.get("/api/v1/documents/nope/approval-logs")) == (404, "DOCUMENT_NOT_FOUND")


# ---- 실제 토큰 권한 (의존성 오버라이드 없이) -------------------------------------
def test_real_token_permissions(client, auth_client, make_doc, user, admin):
    from app.api.deps import get_current_user
    from app.main import app
    doc_id = make_doc("approve")
    app.dependency_overrides.pop(get_current_user, None)
    user_h = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    admin_h = {"Authorization": f"Bearer {create_access_token(admin.id)}"}

    assert client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept"},
                       headers=user_h).status_code == 200          # USER 도 처분 가능
    r = client.post(f"/api/v1/documents/{doc_id}/cancel-approval", json={"reason": "x"}, headers=user_h)
    assert err(r) == (403, "FORBIDDEN")                               # 취소는 ADMIN 만
    assert client.post(f"/api/v1/documents/{doc_id}/cancel-approval", json={"reason": "x"},
                       headers=admin_h).status_code == 200
    assert client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept"}).status_code == 401


# ---- 대시보드 연동 (홍채령 님 집계가 처분 결과를 읽는지) ---------------------------
def test_dashboard_counts_dispositions(auth_client, make_doc):
    approve(auth_client, make_doc("approve"), "accept")
    approve(auth_client, make_doc("reject"), "conditional_accept", "조건부 사용")
    hold(auth_client, make_doc("hold"))
    d = auth_client.get("/api/v1/dashboard/summary").json()["data"]
    assert (d["total_processed"], d["accept_count"], d["conditional_accept_count"], d["on_hold_count"]) == (2, 1, 1, 1)
