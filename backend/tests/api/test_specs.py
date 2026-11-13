"""[담당: 장수민] 규격 API 테스트 — GET /specs, GET /specs/sets, PATCH /specs/{id} (명세 4.20, 4.21). 실제 DB 필요."""
import pytest

from app.core.enums import SpecType
from app.models import SpecItem, SpecSet

Q = SpecType.QUANTITATIVE


@pytest.fixture
def sets(db):
    d1 = SpecSet(code="LI2CO3-D1", material_code="LI2CO3", material_name="탄산리튬", grade="D1",
                 version="YS/T 582-2023", is_default=True)
    d1.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=Q, source="D1"),
                SpecItem(item_name="순도", unit="%", lsl=99.5, spec_type=Q, source="D1"),
                SpecItem(item_name="Mg", unit="ppm", usl=10, spec_type=Q, is_required=False)]
    d3 = SpecSet(code="LI2CO3-D3", material_code="LI2CO3", material_name="탄산리튬", grade="D3",
                 version="YS/T 582-2023", is_default=False)
    d3.items = [SpecItem(item_name="Na", unit="ppm", usl=250, spec_type=Q)]
    lioh = SpecSet(code="LIOH-D1", material_code="LIOH", material_name="수산화리튬", grade="D1", is_default=True)
    lioh.items = [SpecItem(item_name="Na", unit="ppm", usl=30, spec_type=Q)]
    db.add_all([d1, d3, lioh])
    db.commit()
    return {"d1": d1, "d3": d3, "lioh": lioh}


def na_id(sets, key="d1"):
    return next(i.id for i in sets[key].items if i.item_name == "Na")


# ---- 조회 (4.20) ------------------------------------------------------------
def test_list_all(auth_client, sets):
    data = auth_client.get("/api/v1/specs").json()["data"]
    assert len(data) == 5
    na = data[0]
    assert (na["material_code"], na["material_name"], na["item_name"], na["usl"], na["grade"]) == \
        ("LI2CO3", "탄산리튬", "Na", 50, "D1")
    assert (na["spec_set_code"], na["version"], na["is_required"], na["spec_type"]) == \
        ("LI2CO3-D1", "YS/T 582-2023", True, "정량")


def test_filter_by_material_and_set(auth_client, sets):
    assert {d["spec_set_code"] for d in auth_client.get("/api/v1/specs?material_code=LI2CO3").json()["data"]} == \
        {"LI2CO3-D1", "LI2CO3-D3"}
    data = auth_client.get("/api/v1/specs?spec_set_code=LI2CO3-D3").json()["data"]
    assert [(d["item_name"], d["usl"]) for d in data] == [("Na", 250)]


def test_list_sets(auth_client, sets):
    data = auth_client.get("/api/v1/specs/sets?material_code=LI2CO3").json()["data"]
    assert [(d["code"], d["is_default"], d["item_count"]) for d in data] == [
        ("LI2CO3-D1", True, 3), ("LI2CO3-D3", False, 1),     # 기본 세트가 먼저
    ]


def test_list_requires_login(client, sets):
    assert client.get("/api/v1/specs").status_code == 401


# ---- 수정 (4.21) ------------------------------------------------------------
def test_admin_updates_spec(auth_client, sets, admin):
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 40, "reason": "규격 개정"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert (d["usl"], d["unit"], d["updated_by"]) == (40, "ppm", "관리자")   # 보내지 않은 unit 은 그대로
    assert d["updated_at"].endswith("+09:00")


def test_null_clears_limit(auth_client, sets, admin):
    auth_client.login_as(admin)
    purity = next(i.id for i in sets["d1"].items if i.item_name == "순도")
    d = auth_client.patch(f"/api/v1/specs/{purity}", json={"lsl": None, "reason": "하한 삭제"}).json()["data"]
    assert d["lsl"] is None


@pytest.mark.parametrize("body", [{"lsl": 60}, {"lsl": 10, "usl": 5}])
def test_invalid_range(auth_client, sets, admin, body):
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={**body, "reason": "규격 개정"})   # Na 상한 50 보다 큰 하한
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SPEC_RANGE"


def test_update_forbidden_for_user(auth_client, sets):
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 40, "reason": "규격 개정"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_update_not_found(auth_client, sets, admin):
    auth_client.login_as(admin)
    r = auth_client.patch("/api/v1/specs/99999", json={"usl": 1, "reason": "규격 개정"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "SPEC_NOT_FOUND"


def test_update_applies_to_new_documents_only(auth_client, sets, admin, db):
    """명세 4.21: 수정한 규격은 이후 업로드 문서부터. 이미 판정한 문서는 그대로."""
    pdf = b"%PDF-1.7\n" + b"0" * 50
    before = auth_client.post("/api/v1/documents", files={"file": ("a.pdf", pdf)},
                              data={"material_code": "LI2CO3"}).json()["data"]["document_id"]
    auth_client.login_as(admin)
    auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 10, "reason": "D1 개정"})   # 목업 Na "< 20" → 이제 판정 불가
    after = auth_client.post("/api/v1/documents", files={"file": ("a.pdf", pdf)},
                             data={"material_code": "LI2CO3"}).json()["data"]["document_id"]

    def na_judgement(doc_id):
        items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
        return next(i["judgement"] for i in items if i["normalized_name"] == "Na")
    assert (na_judgement(before), na_judgement(after)) == ("pass", "undetermined")


# ---- 변경 사유·이력 (v1.4) --------------------------------------------------
def change_logs(client, spec_id):
    r = client.get(f"/api/v1/specs/{spec_id}/change-logs")
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_update_requires_reason(auth_client, sets, admin, reason):
    auth_client.login_as(admin)
    body = {"usl": 40} if reason is None else {"usl": 40, "reason": reason}
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "REASON_REQUIRED"
    assert auth_client.get("/api/v1/specs?spec_set_code=LI2CO3-D1").json()["data"][0]["usl"] == 50   # 그대로
    assert change_logs(auth_client, na_id(sets)) == []


def test_update_check_order(auth_client, sets, admin):
    # 규격 없음 404 → 사유 누락 400 → 범위 오류 400
    auth_client.login_as(admin)
    assert auth_client.patch("/api/v1/specs/99999", json={"usl": 1}).json()["error"]["code"] == "SPEC_NOT_FOUND"
    assert auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"lsl": 60}).json()["error"]["code"] == \
        "REASON_REQUIRED"


def test_change_log_records_changed_fields_only(auth_client, sets, admin):
    auth_client.login_as(admin)
    na = na_id(sets)
    auth_client.patch(f"/api/v1/specs/{na}", json={"unit": "ppm", "usl": 30, "lsl": None,
                                                   "reason": "  고객사 요구로 강화  "})
    auth_client.patch(f"/api/v1/specs/{na}", json={"lsl": 1, "usl": 40, "reason": "하한 추가"})
    logs = change_logs(auth_client, na)
    # unit(ppm 그대로)·lsl(없음 그대로)은 바뀌지 않아 빠진다. 필드는 lsl → usl → unit 순서
    assert [(log["before_value"], log["after_value"], log["reason"], log["user_name"]) for log in logs] == [
        ("usl: 50", "usl: 30", "고객사 요구로 강화", "관리자"),
        ("lsl: 없음, usl: 30", "lsl: 1, usl: 40", "하한 추가", "관리자"),
    ]
    assert logs[0]["created_at"].endswith("+09:00")


def test_no_change_no_log(auth_client, sets, admin):
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 50, "reason": "확인"})
    assert r.status_code == 200 and r.json()["data"]["updated_by"] == "관리자"   # 수정자는 갱신
    assert change_logs(auth_client, na_id(sets)) == []


def test_change_logs_visible_to_user(auth_client, sets, admin, user):
    auth_client.login_as(admin)
    auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 40, "reason": "규격 개정"})
    auth_client.login_as(user)
    assert [log["after_value"] for log in change_logs(auth_client, na_id(sets))] == ["usl: 40"]


def test_change_logs_not_found(auth_client, sets):
    r = auth_client.get("/api/v1/specs/99999/change-logs")
    assert r.status_code == 404 and r.json()["error"]["code"] == "SPEC_NOT_FOUND"


def test_change_logs_require_login(client, sets):
    assert client.get(f"/api/v1/specs/{na_id(sets)}/change-logs").status_code == 401


# ---- 규격 변경 시 재판정 (10.25 회의 결정) -------------------------------------
PDF = b"%PDF-1.7\n" + b"0" * 50


def upload(client):
    return client.post("/api/v1/documents", files={"file": ("a.pdf", PDF)},
                       data={"material_code": "LI2CO3"}).json()["data"]["document_id"]


def na_judgement(client, doc_id):
    items = client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    return next(i["judgement"] for i in items if i["normalized_name"] == "Na")


def test_rejudge_open_documents(auth_client, sets, admin):
    doc_id = upload(auth_client)
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 10, "reason": "D1 개정", "rejudge": True})
    assert r.status_code == 200, r.text
    rejudged = r.json()["data"]["rejudged_documents"]
    assert [d["document_id"] for d in rejudged] == [doc_id]
    assert "Na" in rejudged[0]["changed_items"]
    assert na_judgement(auth_client, doc_id) == "undetermined"      # 목업 Na "< 20" 이 새 상한 10 보다 넓다


def test_rejudge_off_keeps_old_documents(auth_client, sets, admin):
    doc_id = upload(auth_client)
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 10, "reason": "D1 개정"})
    assert r.json()["data"]["rejudged_documents"] == []
    assert na_judgement(auth_client, doc_id) == "pass"


def test_rejudge_skips_other_spec_sets(auth_client, sets, admin):
    doc_id = upload(auth_client)                                       # 기본 세트(D1)로 판정된 문서
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets, 'd3')}", json={"usl": 10, "reason": "D3 개정", "rejudge": True})
    assert r.json()["data"]["rejudged_documents"] == []
    assert na_judgement(auth_client, doc_id) == "pass"


def test_rejudge_skips_approved_documents(auth_client, sets, admin):
    doc_id = upload(auth_client)
    items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    for i in items:                                                    # 신뢰도 낮은 항목은 확인해야 처분할 수 있다
        if i["confidence"] is not None and i["confidence"] < 0.8:
            auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{i['item_id']}/confirm")
    r = auth_client.post(f"/api/v1/documents/{doc_id}/approve",
                         json={"decision": "conditional_accept", "reason": "재판정 제외 확인용"})
    assert r.status_code == 200, r.text
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na_id(sets)}", json={"usl": 10, "reason": "D1 개정", "rejudge": True})
    assert r.json()["data"]["rejudged_documents"] == []
    assert na_judgement(auth_client, doc_id) == "pass"


# ---- 영향 미리보기·되돌리기 (운영 정책 5장) ------------------------------------
def preview(client, spec_id, **body):
    return client.post(f"/api/v1/specs/{spec_id}/preview", json=body)


def revert(client, spec_id, **body):
    return client.post(f"/api/v1/specs/{spec_id}/revert", json=body)


def current_spec(client, spec_id):
    return next(s for s in client.get("/api/v1/specs").json()["data"] if s["id"] == spec_id)


def test_preview_shows_impact_without_saving(auth_client, sets, admin):
    doc_id = upload(auth_client)
    auth_client.login_as(admin)
    r = preview(auth_client, na_id(sets), usl=10)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["changed_fields"] == ["usl"]
    assert (data["target_documents"], data["affected_documents"]) == (1, 1)
    assert data["documents"][0]["document_id"] == doc_id and "Na" in data["documents"][0]["changed_items"]
    # 아무것도 저장되지 않는다: 규격, 이력, 문서 판정이 그대로
    assert current_spec(auth_client, na_id(sets))["usl"] == 50
    assert change_logs(auth_client, na_id(sets)) == []
    assert na_judgement(auth_client, doc_id) == "pass"


def test_preview_counts_only_changed_recommendations(auth_client, sets, admin):
    """이 목업 문서는 다른 항목 때문에 이미 보류 권고라서, Na 판정이 바뀌어도 권고는 그대로다."""
    upload(auth_client)
    auth_client.login_as(admin)
    data = preview(auth_client, na_id(sets), usl=10).json()["data"]
    d = data["documents"][0]
    assert d["lot_recommendation_before"] == d["lot_recommendation_after"] == "hold"
    assert (data["affected_documents"], data["recommendation_changed_documents"]) == (1, 0)


def test_preview_without_effective_change(auth_client, sets, admin):
    upload(auth_client)
    auth_client.login_as(admin)
    data = preview(auth_client, na_id(sets), usl=50).json()["data"]      # 현재 값과 같다
    assert data["changed_fields"] == [] and data["affected_documents"] == 0 and data["target_documents"] == 1


def test_preview_ignores_other_spec_sets_and_checks_input(auth_client, sets, admin):
    upload(auth_client)
    auth_client.login_as(admin)
    assert preview(auth_client, na_id(sets, "d3"), usl=10).json()["data"]["target_documents"] == 0
    assert preview(auth_client, na_id(sets), lsl=60, usl=10).status_code == 400   # INVALID_SPEC_RANGE
    assert preview(auth_client, 99999, usl=10).status_code == 404


def test_preview_admin_only(auth_client, sets):
    assert preview(auth_client, na_id(sets), usl=10).status_code == 403


def test_revert_restores_previous_values_and_logs(auth_client, sets, admin):
    auth_client.login_as(admin)
    spec_id = na_id(sets)
    auth_client.patch(f"/api/v1/specs/{spec_id}", json={"usl": 40, "unit": "ppb", "reason": "개정"})
    r = revert(auth_client, spec_id, reason="잘못 입력")
    assert r.status_code == 200, r.text
    assert (r.json()["data"]["usl"], r.json()["data"]["unit"]) == (50, "ppm")
    logs = change_logs(auth_client, spec_id)
    assert len(logs) == 2                                                  # 이력은 지우지 않고 한 건이 더 생긴다
    assert logs[-1]["reason"] == "되돌리기: 잘못 입력"
    assert (logs[-1]["before_value"], logs[-1]["after_value"]) == ("usl: 40, unit: ppb", "usl: 50, unit: ppm")


def test_revert_restores_cleared_limit(auth_client, sets, admin):
    auth_client.login_as(admin)
    purity = next(i.id for i in sets["d1"].items if i.item_name == "순도")
    auth_client.patch(f"/api/v1/specs/{purity}", json={"lsl": None, "reason": "하한 삭제"})
    assert current_spec(auth_client, purity)["lsl"] is None
    revert(auth_client, purity, reason="복원")
    assert current_spec(auth_client, purity)["lsl"] == 99.5


def test_revert_twice_returns_to_changed_value(auth_client, sets, admin):
    auth_client.login_as(admin)
    spec_id = na_id(sets)
    auth_client.patch(f"/api/v1/specs/{spec_id}", json={"usl": 40, "reason": "개정"})
    revert(auth_client, spec_id, reason="되돌림")
    revert(auth_client, spec_id, reason="다시 적용")
    assert current_spec(auth_client, spec_id)["usl"] == 40


def test_revert_requires_reason_history_and_admin(auth_client, sets, admin):
    spec_id = na_id(sets)
    assert revert(auth_client, spec_id, reason="사유").status_code == 403
    auth_client.login_as(admin)
    r = revert(auth_client, spec_id, reason="사유")                         # 되돌릴 이력 없음
    assert (r.status_code, r.json()["error"]["code"]) == (409, "NOTHING_TO_REVERT")
    auth_client.patch(f"/api/v1/specs/{spec_id}", json={"usl": 40, "reason": "개정"})
    for reason in (None, "", "  "):
        r = revert(auth_client, spec_id, reason=reason)
        assert (r.status_code, r.json()["error"]["code"]) == (400, "REASON_REQUIRED")
    assert current_spec(auth_client, spec_id)["usl"] == 40
    assert revert(auth_client, 99999, reason="사유").status_code == 404


def test_revert_can_rejudge_open_documents(auth_client, sets, admin):
    doc_id = upload(auth_client)
    auth_client.login_as(admin)
    spec_id = na_id(sets)
    auth_client.patch(f"/api/v1/specs/{spec_id}", json={"usl": 10, "reason": "개정", "rejudge": True})
    assert na_judgement(auth_client, doc_id) == "undetermined"
    r = revert(auth_client, spec_id, reason="되돌림", rejudge=True)
    assert [d["document_id"] for d in r.json()["data"]["rejudged_documents"]] == [doc_id]
    assert na_judgement(auth_client, doc_id) == "pass"
