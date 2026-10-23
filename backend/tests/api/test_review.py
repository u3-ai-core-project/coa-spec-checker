"""[담당: 장수민] 검수 API 테스트 (명세 4.8~4.11). 실제 DB 필요.

추출 결과 조회, 항목 수정·회신값 입력·항목명 수정, 값 확인, 이력.
"""
import json

import pytest

from app.core.config import settings
from app.core.enums import DocumentStatus, SpecType
from app.models import Document, ItemMapping, SpecItem, SpecSet

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100

# 목업 추출 결과 (실제 CoA 아님). 항목마다 시험할 상황이 하나씩 들어 있다.
MOCK = {
    "supplier": "테스트 공급사",
    "lot_no": "LOT-1",
    "items": [
        {"raw_name": "Sodium (Na)", "normalized_name": "Na", "mapping_source": "dictionary",
         "raw_value": "12", "unit": "ppm", "confidence": 0.95},                       # 적합
        {"raw_name": "Iron (Fe)", "normalized_name": "Fe", "mapping_source": "dictionary",
         "raw_value": "none detected", "unit": "ppm", "confidence": 0.95},            # ND_NO_LOD (확인 필요)
        {"raw_name": "Assay", "normalized_name": "순도", "mapping_source": "dictionary",
         "raw_value": "99.6", "unit": "%", "confidence": 0.6},                         # LOW_CONFIDENCE
        {"raw_name": "Calcium content", "normalized_name": "칼슘", "mapping_source": "ai",
         "raw_value": "15", "unit": "ppm", "confidence": 0.9},                         # AI 오매핑 (규격에 없음 → 참고)
        {"raw_name": "Heavy metals (as Pb)", "normalized_name": "중금속 총량", "mapping_source": "dictionary",
         "raw_value": "10", "unit": "ppm", "confidence": 0.95},                        # Pb → AMBIGUOUS_ANALYTE
    ],
}


@pytest.fixture
def doc_id(auth_client, db, tmp_path, monkeypatch):
    """규격 세트 + 목업 추출 결과로 문서 1건을 extracted 상태까지 만든다."""
    q = SpecType.QUANTITATIVE
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [
        SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=q),
        SpecItem(item_name="Fe", unit="ppm", usl=5, spec_type=q),
        SpecItem(item_name="순도", unit="%", lsl=99.5, spec_type=q),
        SpecItem(item_name="Ca", unit="ppm", usl=20, spec_type=q),
        SpecItem(item_name="Pb", unit="ppm", usl=3, spec_type=q),
        SpecItem(item_name="중금속 총량", unit="ppm", spec_type=q, is_required=False),
    ]
    db.add(spec_set)
    db.commit()

    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "coa.json").write_text(json.dumps(MOCK, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    r = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)}, data={"material_code": "LI2CO3"})
    assert r.status_code == 201
    return r.json()["data"]["document_id"]


def items_of(client, doc_id) -> dict:
    data = client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]
    return {i["normalized_name"]: i for i in data["items"]}


def item_id(client, doc_id, name) -> str:
    return items_of(client, doc_id)[name]["item_id"]


def patch(client, doc_id, name, **body):
    """항목 수정. 사유(reason)는 따로 주지 않으면 기본값을 넣는다 (v1.4: 값 수정은 사유 필수). 빼려면 reason=None."""
    body.setdefault("reason", "원문 대조 후 수정")
    body = {k: v for k, v in body.items() if v is not None or k != "reason"}
    return client.patch(f"/api/v1/documents/{doc_id}/extraction/{item_id(client, doc_id, name)}", json=body)


def confirm(client, doc_id, name):
    return client.post(f"/api/v1/documents/{doc_id}/extraction/{item_id(client, doc_id, name)}/confirm")


# ---- 조회 (4.8) ------------------------------------------------------------
def test_get_extraction(auth_client, doc_id):
    r = auth_client.get(f"/api/v1/documents/{doc_id}/extraction")
    assert r.status_code == 200
    data = r.json()["data"]
    items = {i["normalized_name"]: i for i in data["items"]}
    assert items["Fe"]["reason_code"] == "ND_NO_LOD"
    assert items["순도"]["reason_code"] == "LOW_CONFIDENCE"
    assert items["Ca"]["reason_code"] == "MISSING_REQUIRED"
    assert items["Pb"]["reason_code"] == "AMBIGUOUS_ANALYTE"
    assert items["칼슘"]["judgement_reason"] == "규격 없음"
    assert data["lot_recommendation"] == "hold" and data["summary"]["pass"] >= 1


def test_get_extraction_not_ready(auth_client, doc_id, db):
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.FAILED
    db.commit()
    r = auth_client.get(f"/api/v1/documents/{doc_id}/extraction")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_READY"


def test_get_extraction_not_found(auth_client, doc_id):
    assert auth_client.get("/api/v1/documents/nope/extraction").json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# ---- 회신값 입력 → 자동 재판정 (v1.4안) ---------------------------------------
def test_detection_limit_reply_resolves_nd(auth_client, doc_id, db):
    r = patch(auth_client, doc_id, "Fe", detection_limit=2, value_source="supplier_reply")
    assert r.status_code == 200
    body = r.json()["data"]
    item = body["item"]
    assert (item["judgement"], item["reason_code"], item["resolution"]) == ("pass", None, None)
    assert (item["value_qualifier"], item["detection_limit"], item["value_source"]) == ("not_detected", 2, "supplier_reply")
    log = body["review_logs"][0]
    assert (log["action"], log["value_source"], log["reviewer_name"]) == ("edit", "supplier_reply", "김사용")
    assert (log["before_value"], log["after_value"]) == ("none detected", "검출 안 됨 (검출한계 2 ppm)")

    doc = db.get(Document, doc_id)
    db.refresh(doc)
    assert doc.status == "in_review" and doc.extraction.result["review_status"] == "in_review"


def test_reply_not_meeting_condition_stays_exception(auth_client, doc_id):
    item = patch(auth_client, doc_id, "Fe", detection_limit=10).json()["data"]["item"]
    assert (item["judgement"], item["reason_code"]) == ("undetermined", "LOD_ABOVE_LIMIT")


def test_edit_value_recalculates_judgement_and_lot(auth_client, doc_id):
    body = patch(auth_client, doc_id, "Na", converted_value=80).json()["data"]
    assert (body["item"]["judgement"], body["item"]["reason_code"], body["item"]["deviation"]) == ("fail", "OUT_OF_SPEC", 30)
    assert body["lot_recommendation"] == "reject" and body["summary"]["fail"] == 1
    assert body["review_logs"][0]["value_source"] == "correction"   # 기본값


def test_internal_test_value_for_missing_item(auth_client, doc_id):
    item = patch(auth_client, doc_id, "Ca", converted_value=8, value_source="internal_test").json()["data"]["item"]
    assert (item["judgement"], item["value_source"]) == ("pass", "internal_test")


def test_pb_single_value_is_kept_after_other_edits(auth_client, doc_id):
    patch(auth_client, doc_id, "Pb", converted_value=1, value_source="supplier_reply")
    patch(auth_client, doc_id, "Na", converted_value=10)     # 다른 항목 수정 → 교차 규칙 재실행
    pb = items_of(auth_client, doc_id)["Pb"]
    assert (pb["judgement"], pb["converted_value"]) == ("pass", 1)


def test_resolving_all_exceptions_makes_approve(auth_client, doc_id):
    patch(auth_client, doc_id, "Fe", detection_limit=2, value_source="supplier_reply")
    confirm(auth_client, doc_id, "순도")
    patch(auth_client, doc_id, "칼슘", normalized_name="Ca")
    body = patch(auth_client, doc_id, "Pb", converted_value=1, value_source="supplier_reply").json()["data"]
    assert body["lot_recommendation"] == "approve"
    assert body["summary"] == {"pass": 6, "fail": 0, "undetermined": 0, "missing": 0, "check": 0}


# ---- 값 확인 (4.10) ----------------------------------------------------------
def test_confirm_low_confidence(auth_client, doc_id):
    body = confirm(auth_client, doc_id, "순도").json()["data"]
    assert (body["item"]["judgement"], body["item"]["reason_code"], body["item"]["reviewed"]) == ("pass", None, True)
    log = body["review_log"]
    assert log["action"] == "confirm" and log["before_value"] == log["after_value"] == "99.6"


def test_confirm_does_not_fix_missing_detection_limit(auth_client, doc_id):
    item = confirm(auth_client, doc_id, "Fe").json()["data"]["item"]
    assert (item["judgement"], item["reason_code"]) == ("check", "ND_NO_LOD")


def test_confirm_missing_item_rejected(auth_client, doc_id):
    r = confirm(auth_client, doc_id, "Ca")
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


# ---- 항목명 수정 ------------------------------------------------------------
def test_rename_rejudges_and_removes_missing_item(auth_client, doc_id, db):
    body = patch(auth_client, doc_id, "칼슘", normalized_name="Ca").json()["data"]
    assert (body["item"]["normalized_name"], body["item"]["judgement"]) == ("Ca", "pass")   # 15 ≤ 20
    assert body["review_logs"][0]["action"] == "rename"
    names = [i for i in items_of(auth_client, doc_id).values() if i["normalized_name"] == "Ca"]
    assert len(names) == 1 and names[0]["mapping_source"] == "manual"   # 기존 Ca 누락 항목은 사라짐

    m = db.query(ItemMapping).filter_by(material_code="LI2CO3", raw_name="Calcium content").one()
    assert (m.normalized_name, m.source) == ("Ca", "manual")


def test_rename_keeps_entered_value(auth_client, doc_id):
    patch(auth_client, doc_id, "칼슘", converted_value=30)              # 규격 없는 상태에서 값 수정
    item = patch(auth_client, doc_id, "칼슘", normalized_name="Ca").json()["data"]["item"]
    assert (item["judgement"], item["converted_value"]) == ("fail", 30)   # 입력값 30 > 20 으로 다시 판정


def test_rename_away_creates_missing_item(auth_client, doc_id):
    patch(auth_client, doc_id, "칼슘", normalized_name="Ca")
    patch(auth_client, doc_id, "Ca", normalized_name="Pb")  # Pb 누락 항목이 있던 자리 → 허용 (값 없는 누락)
    items = items_of(auth_client, doc_id)
    assert items["Ca"]["mapping_source"] == "spec" and items["Ca"]["judgement"] == "missing"
    assert items["Pb"]["mapping_source"] == "manual"


def test_rename_and_edit_in_one_request(auth_client, doc_id):
    body = patch(auth_client, doc_id, "칼슘", normalized_name="Ca", converted_value=25).json()["data"]
    assert [log["action"] for log in body["review_logs"]] == ["rename", "edit"]
    assert body["item"]["judgement"] == "fail"


def test_rename_unknown_name(auth_client, doc_id):
    r = patch(auth_client, doc_id, "칼슘", normalized_name="마그네슘")
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNKNOWN_ITEM_NAME"


def test_rename_to_name_already_present(auth_client, doc_id):
    r = patch(auth_client, doc_id, "칼슘", normalized_name="Na")
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rename_missing_item_rejected(auth_client, doc_id):
    r = patch(auth_client, doc_id, "Ca", normalized_name="Fe")
    assert r.status_code == 400


# ---- 요청 형식 --------------------------------------------------------------
@pytest.mark.parametrize("body", [
    {},                                                        # 아무것도 없음
    {"converted_value": "abc"},                                # 숫자 아님
    {"converted_value": 5, "detection_limit": 1},              # exact 인데 검출한계
    {"value_qualifier": "not_detected", "converted_value": 3}, # 검출 안 됨인데 값
    {"value_qualifier": "text", "converted_value": 3},         # text 인데 숫자
    {"normalized_name": "Ca", "value_source": "supplier_reply"},  # 값 없이 출처만
    {"detection_limit": -1},                                   # 음수
])
def test_invalid_body(auth_client, doc_id, body):
    r = patch(auth_client, doc_id, "Na", **body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_numeric_string_value_accepted(auth_client, doc_id):
    assert patch(auth_client, doc_id, "Na", converted_value="40").json()["data"]["item"]["converted_value"] == 40


def test_less_than_value(auth_client, doc_id):
    item = patch(auth_client, doc_id, "Fe", converted_value=10, value_qualifier="less_than").json()["data"]["item"]
    assert (item["judgement"], item["reason_code"]) == ("undetermined", "BOUND_ABOVE_LIMIT")


# ---- 상태 ------------------------------------------------------------------
def test_item_not_found(auth_client, doc_id):
    r = auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/nope", json={"converted_value": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "ITEM_NOT_FOUND"


@pytest.mark.parametrize("status, code", [
    (DocumentStatus.APPROVED, "ALREADY_APPROVED"),
    (DocumentStatus.QUEUED, "NOT_READY"),
    (DocumentStatus.PROCESSING, "NOT_READY"),
])
def test_edit_blocked_by_status(auth_client, doc_id, db, status, code):
    fe = item_id(auth_client, doc_id, "Fe")
    doc = db.get(Document, doc_id)
    doc.status = status
    db.commit()
    for r in (auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{fe}", json={"detection_limit": 1}),
              auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{fe}/confirm")):
        assert r.status_code == 409 and r.json()["error"]["code"] == code


def test_on_hold_goes_back_to_in_review(auth_client, doc_id, db):
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.ON_HOLD
    db.commit()
    confirm(auth_client, doc_id, "순도")
    db.refresh(doc)
    assert doc.status == "in_review"


def test_requires_login(client, auth_client, doc_id):
    from app.api.deps import get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get(f"/api/v1/documents/{doc_id}/extraction").status_code == 401


# ---- 수정 사유 (v1.4) --------------------------------------------------------
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_edit_value_requires_reason(auth_client, doc_id, reason):
    before = items_of(auth_client, doc_id)["Na"]
    r = patch(auth_client, doc_id, "Na", converted_value=80, reason=reason)
    assert r.status_code == 400 and r.json()["error"]["code"] == "REASON_REQUIRED"
    assert items_of(auth_client, doc_id)["Na"] == before                               # 아무것도 바뀌지 않음
    assert auth_client.get(f"/api/v1/documents/{doc_id}/review-logs").json()["data"] == []


def test_reply_value_requires_reason(auth_client, doc_id):
    r = patch(auth_client, doc_id, "Fe", detection_limit=2, value_source="supplier_reply", reason=None)
    assert r.status_code == 400 and r.json()["error"]["code"] == "REASON_REQUIRED"


def test_rename_only_does_not_require_reason(auth_client, doc_id):
    r = patch(auth_client, doc_id, "칼슘", normalized_name="Ca", reason=None)
    assert r.status_code == 200
    assert r.json()["data"]["review_logs"][0]["reason"] is None


def test_reason_saved_on_every_log_of_the_request(auth_client, doc_id):
    body = patch(auth_client, doc_id, "칼슘", normalized_name="Ca", converted_value=25,
                 reason="  OCR 오인식 정정 (원본 2.5)  ").json()["data"]
    assert [(log["action"], log["reason"]) for log in body["review_logs"]] == [
        ("rename", "OCR 오인식 정정 (원본 2.5)"), ("edit", "OCR 오인식 정정 (원본 2.5)"),   # 앞뒤 공백 제거
    ]


def test_reason_in_review_logs(auth_client, doc_id):
    confirm(auth_client, doc_id, "순도")
    patch(auth_client, doc_id, "Fe", detection_limit=2, value_source="supplier_reply", reason="공급사 회신 메일")
    logs = auth_client.get(f"/api/v1/documents/{doc_id}/review-logs").json()["data"]
    assert [(log["action"], log["reason"]) for log in logs] == [("confirm", None), ("edit", "공급사 회신 메일")]


def test_status_checked_before_reason(auth_client, doc_id, db):
    # 검사 순서: 상태 409 가 사유 누락 400 보다 먼저
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.APPROVED
    db.commit()
    r = patch(auth_client, doc_id, "Na", converted_value=80, reason=None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_APPROVED"


# ---- 이력 (4.11) -------------------------------------------------------------
def test_review_logs_in_order(auth_client, doc_id, admin):
    confirm(auth_client, doc_id, "순도")
    auth_client.login_as(admin)
    patch(auth_client, doc_id, "칼슘", normalized_name="Ca", converted_value=5)
    logs = auth_client.get(f"/api/v1/documents/{doc_id}/review-logs").json()["data"]
    assert [(log["action"], log["reviewer_name"]) for log in logs] == [
        ("confirm", "김사용"), ("rename", "관리자"), ("edit", "관리자"),
    ]
    assert logs[0]["reviewed_at"].endswith("+09:00")
