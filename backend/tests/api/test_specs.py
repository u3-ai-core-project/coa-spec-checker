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
