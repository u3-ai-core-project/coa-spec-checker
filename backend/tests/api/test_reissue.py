"""[담당: 장수민] 재발행 버전 충돌 테스트 (운영 정책 8.2). 실제 DB 필요.

같은 원자재·같은 로트의 CoA 가 또 들어오면 충돌로 표시하고, 기준 버전을 고르기 전에는 확정 처분을 막는다.
이미 처분된 로트에 재발행본이 들어오면 처분은 그대로 두고 재검토 대상으로 알린다.
"""
import json

import pytest

from app.core.config import settings
from app.core.enums import SpecType
from app.models import SpecItem, SpecSet

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


def mock(lot, na="12"):
    return {"lot_no": lot, "items": [{"raw_name": "Na", "normalized_name": "Na", "mapping_source": "dictionary",
                                      "raw_value": na, "unit": "ppm", "confidence": 0.95}]}


@pytest.fixture
def make_doc(auth_client, db, tmp_path, monkeypatch):
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _make(name: str, lot: str | None, na: str = "12", material: str = "LI2CO3") -> str:
        data = mock(lot, na)
        if lot is None:
            del data["lot_no"]
        (mock_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        r = auth_client.post("/api/v1/documents", files={"file": (f"{name}.pdf", PDF)}, data={"material_code": material})
        assert r.status_code == 201, r.text
        return r.json()["data"]["document_id"]
    return _make


def info(client, doc_id):
    r = client.get(f"/api/v1/reissue/{doc_id}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def choose(client, doc_id, base_id, reason="최신본 사용"):
    return client.post(f"/api/v1/reissue/{doc_id}/base", json={"base_document_id": base_id, "reason": reason})


def approve(client, doc_id):
    return client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept", "reason": None})


def code(r):
    return r.json()["error"]["code"]


def test_single_document_has_no_conflict(auth_client, make_doc):
    doc = make_doc("a", "L-001")
    assert info(auth_client, doc) == {"status": "none", "material_code": "LI2CO3", "lot_no": "L-001",
                                      "base_document_id": None, "decided_reason": None, "versions": []}
    assert approve(auth_client, doc).status_code == 200      # 충돌이 없으면 기존처럼 처분된다


def test_same_lot_is_conflict_ignoring_case_space_and_separators(auth_client, make_doc):
    first = make_doc("a", "L-001")
    second = make_doc("b", "l 001")
    for doc in (first, second):
        data = info(auth_client, doc)
        assert data["status"] == "conflict"
        assert [v["document_id"] for v in data["versions"]] == [first, second]       # 올린 순서, 나란히 보여 줄 목록
    detail = auth_client.get(f"/api/v1/documents/{second}").json()["data"]
    assert detail["reissue_status"] == "conflict"


def test_different_lot_or_material_or_missing_lot_is_not_conflict(auth_client, make_doc, db):
    first = make_doc("a", "L-001")
    make_doc("b", "L-002")
    make_doc("c", None)
    assert info(auth_client, first)["status"] == "none"
    assert auth_client.get("/api/v1/reissue/conflicts").json()["data"] == []


def test_approval_is_blocked_until_base_is_chosen(auth_client, make_doc):
    first = make_doc("a", "L-001")
    second = make_doc("b", "L-001", na="30")
    for doc in (first, second):
        r = approve(auth_client, doc)
        assert (r.status_code, code(r)) == (409, "REISSUE_UNRESOLVED")
    # 보류는 막지 않는다
    r = auth_client.post(f"/api/v1/documents/{first}/hold", json={"follow_up": "request_reissue", "reason": "확인 중"})
    assert r.status_code == 200, r.text


def test_choose_base_then_only_base_can_be_approved(auth_client, make_doc):
    first = make_doc("a", "L-001")
    second = make_doc("b", "L-001")
    r = choose(auth_client, first, second, reason="재발행본이 최신")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert (data["status"], data["base_document_id"], data["decided_reason"]) == ("resolved", second, "재발행본이 최신")
    assert [(v["document_id"], v["is_base"]) for v in data["versions"]] == [(first, False), (second, True)]
    r = approve(auth_client, first)
    assert (r.status_code, code(r)) == (409, "NOT_BASE_VERSION")
    assert approve(auth_client, second).status_code == 200


def test_choose_base_validation(auth_client, make_doc):
    first = make_doc("a", "L-001")
    alone = make_doc("c", "L-009")
    other = make_doc("b", "L-001")
    for reason in (None, "", "  "):
        r = choose(auth_client, first, other, reason=reason)
        assert (r.status_code, code(r)) == (400, "REASON_REQUIRED")
    assert choose(auth_client, first, alone).status_code == 400          # 다른 로트 문서
    assert choose(auth_client, alone, alone).status_code == 400          # 충돌이 없는 문서
    assert choose(auth_client, "no-such-id", first).status_code == 404
    assert auth_client.get("/api/v1/reissue/no-such-id").status_code == 404


def test_new_reissue_after_decision_requires_new_choice(auth_client, make_doc):
    first = make_doc("a", "L-001")
    second = make_doc("b", "L-001")
    choose(auth_client, first, first)
    assert info(auth_client, first)["status"] == "resolved"
    third = make_doc("c", "L-001")                                          # 선택 뒤에 또 재발행
    assert info(auth_client, first)["status"] == "conflict"
    assert approve(auth_client, first).status_code == 409
    choose(auth_client, third, third)
    assert info(auth_client, second)["status"] == "resolved" and info(auth_client, second)["base_document_id"] == third
    assert approve(auth_client, third).status_code == 200


def test_reissue_after_approval_marks_review_needed_without_changing_decision(auth_client, make_doc):
    first = make_doc("a", "L-001")
    assert approve(auth_client, first).status_code == 200
    second = make_doc("b", "L-001", na="80")                                # 이미 처분된 로트의 재발행본
    assert info(auth_client, first)["status"] == "review_needed"
    assert info(auth_client, second)["status"] == "review_needed"
    old = auth_client.get(f"/api/v1/documents/{first}").json()["data"]
    assert (old["status"], old["final_decision"]) == ("approved", "accept")   # 처분은 자동으로 바뀌지 않는다
    groups = auth_client.get("/api/v1/reissue/conflicts").json()["data"]
    assert [(g["status"], g["document_ids"]) for g in groups] == [("review_needed", [first, second])]
    assert approve(auth_client, second).status_code == 409                    # 기준 버전을 고르기 전에는 처분 불가
    choose(auth_client, first, first, reason="기존 처분 유지")
    assert info(auth_client, first)["status"] == "resolved"
    assert auth_client.get("/api/v1/reissue/conflicts").json()["data"] == []


def test_deleting_a_version_dissolves_the_conflict(auth_client, make_doc):
    first = make_doc("a", "L-001")
    second = make_doc("b", "L-001")
    assert info(auth_client, first)["status"] == "conflict"
    assert auth_client.delete(f"/api/v1/documents/{second}").status_code == 200
    assert info(auth_client, first)["status"] == "none"
    assert approve(auth_client, first).status_code == 200


def test_reissue_requires_login(client):
    assert client.get("/api/v1/reissue/conflicts").status_code == 401
    assert client.get("/api/v1/reissue/x").status_code == 401
