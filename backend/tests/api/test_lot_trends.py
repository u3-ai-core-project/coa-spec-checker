"""[담당: 홍채령] 로트별 이탈 추이 API 테스트 (GET /dashboard/lot-trends, 명세 4.19 확장)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.enums import DocumentStatus as S, FinalDecision as D, LotRecommendation as R
from app.models import Document, ExtractionResult

KST = ZoneInfo("Asia/Seoul")
URL = "/api/v1/dashboard/lot-trends"
DAY = datetime(2026, 10, 5, 9, 0, tzinfo=KST)


def na(value, judgement="pass", qualifier="exact", usl=50.0, unit="ppm"):
    return {"normalized_name": "Na", "converted_value": value, "value_qualifier": qualifier, "judgement": judgement,
            "spec_unit": unit, "spec_lsl": None, "spec_usl": usl}


def make_doc(db, uploader, lot, items, approved_at=DAY, status=S.APPROVED, supplier="Chengxin", material="LI2CO3"):
    doc = Document(
        file_name=f"{lot}.pdf", file_path="x", file_size=1, content_type="application/pdf",
        material_code=material, supplier=supplier, lot_no=lot, status=status,
        lot_recommendation=R.APPROVE, final_decision=D.ACCEPT if status == S.APPROVED else None,
        uploaded_by=uploader.id, uploaded_at=approved_at - timedelta(minutes=10),
        approved_by=uploader.id if status == S.APPROVED else None,
        approved_at=approved_at if status == S.APPROVED else None,
    )
    doc.extraction = ExtractionResult(result={"items": items})
    db.add(doc)
    db.commit()
    return doc


def get(client, **params):
    r = client.get(URL, params={"item_name": "Na", **params})
    return r.status_code, r.json()


def test_points_in_approval_order(auth_client, db, user):
    make_doc(db, user, "L2", [na(30.0)], approved_at=DAY + timedelta(days=2))
    make_doc(db, user, "L1", [na(12.0), {"normalized_name": "Fe", "converted_value": 1.0, "judgement": "pass"}])
    make_doc(db, user, "L3", [na(80.0, "fail", usl=40.0)], approved_at=DAY + timedelta(days=5))

    code, body = get(auth_client)

    assert code == 200
    data = body["data"]
    assert [p["lot_no"] for p in data["points"]] == ["L1", "L2", "L3"]
    assert data["points"][0] == {"lot_no": "L1", "supplier": "Chengxin", "value": 12.0, "value_qualifier": "exact",
                                 "judgement": "pass", "approved_at": "2026-10-05T09:00:00+09:00"}
    assert data["points"][2]["judgement"] == "fail"
    # 기준선은 가장 최근 처분 문서(L3)의 규격
    assert (data["item_name"], data["unit"], data["spec_lsl"], data["spec_usl"]) == ("Na", "ppm", None, 40.0)


def test_non_numeric_and_upper_bound_values(auth_client, db, user):
    """검출 안 됨처럼 숫자가 아닌 값은 value null, '< 20' 같은 상한값은 qualifier 로 구분."""
    make_doc(db, user, "L1", [na(None, "undetermined", "not_detected")])
    make_doc(db, user, "L2", [na(20.0, "pass", "less_than")], approved_at=DAY + timedelta(days=1))
    points = get(auth_client)[1]["data"]["points"]
    assert [(p["value"], p["value_qualifier"], p["judgement"]) for p in points] == [
        (None, "not_detected", "undetermined"), (20.0, "less_than", "pass")]


def test_only_approved_documents_with_the_item(auth_client, db, user):
    make_doc(db, user, "L1", [na(12.0)])
    make_doc(db, user, "L2", [na(99.0)], status=S.ON_HOLD)                       # 처분 전
    make_doc(db, user, "L3", [{"normalized_name": "Fe", "converted_value": 1.0, "judgement": "pass"}])  # Na 없음
    assert [p["lot_no"] for p in get(auth_client)[1]["data"]["points"]] == ["L1"]


def test_empty_when_no_points(auth_client, db):
    code, body = get(auth_client)
    assert code == 200
    assert body["data"] == {"item_name": "Na", "unit": None, "spec_lsl": None, "spec_usl": None, "points": []}


def test_filters_period_and_material(auth_client, db, user):
    make_doc(db, user, "L1", [na(1.0)], approved_at=datetime(2026, 10, 1, 23, 50, tzinfo=KST))
    make_doc(db, user, "L2", [na(2.0)], approved_at=datetime(2026, 10, 2, 0, 10, tzinfo=KST))
    make_doc(db, user, "L3", [na(3.0)], approved_at=datetime(2026, 10, 2, 9, 0, tzinfo=KST), material="LIOH")
    lots = lambda **p: [x["lot_no"] for x in get(auth_client, **p)[1]["data"]["points"]]  # noqa: E731
    assert lots(**{"from": "2026-10-02"}) == ["L2", "L3"]                         # 한국 시간 날짜 기준
    assert lots(to="2026-10-01") == ["L1"]
    assert lots(material_code="LIOH") == ["L3"]


def test_scope_like_summary(auth_client, db, user, admin):
    """권한은 4.18 과 같다: USER 는 본인 건만, ADMIN 은 전체와 담당자 필터."""
    make_doc(db, user, "MINE", [na(1.0)])
    make_doc(db, admin, "ADMIN", [na(2.0)], approved_at=DAY + timedelta(days=1))
    assert [p["lot_no"] for p in get(auth_client)[1]["data"]["points"]] == ["MINE"]
    assert get(auth_client, scope="all")[0] == 403
    assert get(auth_client, user_id=admin.id)[0] == 403

    auth_client.login_as(admin)
    assert [p["lot_no"] for p in get(auth_client)[1]["data"]["points"]] == ["MINE", "ADMIN"]
    assert [p["lot_no"] for p in get(auth_client, user_id=user.id)[1]["data"]["points"]] == ["MINE"]


@pytest.mark.parametrize("params", [{}, {"item_name": ""}])
def test_item_name_required(auth_client, db, params):
    r = auth_client.get(URL, params=params)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_requires_login(client, db):
    assert client.get(URL, params={"item_name": "Na"}).status_code == 401
