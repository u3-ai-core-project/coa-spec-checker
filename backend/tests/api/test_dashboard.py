"""[담당: 홍채령]"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.enums import DocumentStatus as S, FinalDecision as D, LotRecommendation as R
from app.models import Document, ExtractionResult

KST = ZoneInfo("Asia/Seoul")
URL = "/api/v1/dashboard/summary"


def make_doc(db, uploader, status, rec=None, decision=None, items=(), uploaded_at=None, minutes=10,
             material_code="LI2CO3"):
    """items: (항목명, 판정) 또는 항목 dict 목록. 처분 일시는 업로드 minutes 분 뒤."""
    uploaded_at = uploaded_at or datetime(2026, 10, 5, 9, 0, tzinfo=KST)
    doc = Document(
        file_name="coa.pdf",
        file_path="x",
        file_size=1,
        content_type="application/pdf",
        material_code=material_code,
        status=status,
        lot_recommendation=rec,
        final_decision=decision,
        uploaded_by=uploader.id,
        uploaded_at=uploaded_at,
        approved_by=uploader.id if status == S.APPROVED else None,
        approved_at=uploaded_at + timedelta(minutes=minutes) if status == S.APPROVED else None,
    )
    doc.extraction = ExtractionResult(
        result={"items": [i if isinstance(i, dict) else {"normalized_name": i[0], "judgement": i[1]} for i in items]}
    )
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture
def docs(db, user, admin):
    """user 문서 4건 (승인 2, 불합격 1, 보류 1), admin 문서 1건 (조건부 승인)."""
    make_doc(db, user, S.APPROVED, R.APPROVE, D.ACCEPT, [("순도", "pass")], minutes=10)
    make_doc(db, user, S.APPROVED, R.HOLD, D.ACCEPT, [("수분", "undetermined")], minutes=20)
    make_doc(db, user, S.APPROVED, R.REJECT, D.REJECT, [("수분", "fail"), ("Na", "fail")], minutes=30)
    make_doc(db, user, S.ON_HOLD, R.HOLD, items=[("Fe", "fail")])  # 처분 전이라 deviation 집계 제외
    make_doc(
        db, admin, S.APPROVED, R.REJECT, D.CONDITIONAL_ACCEPT, [("수분", "fail")],
        uploaded_at=datetime(2026, 10, 8, 23, 50, tzinfo=KST), minutes=20,  # 처분은 10/9 00:10 (KST)
    )


def test_user_default_is_mine(auth_client, docs):
    data = auth_client.get(URL).json()["data"]
    assert data == {
        "total_processed": 3,
        "accept_count": 2,
        "conditional_accept_count": 0,
        "reject_count": 1,
        "on_hold_count": 1,
        "pass_rate": 66.7,
        "avg_processing_time_sec": 1200.0,
        "recommendation_match_rate": 100.0,  # 승인→승인, 불합격→불합격 일치. 보류 권고 문서는 계산에서 제외
        "auto_approve_rate": 50.0,           # 정상(승인) 2건 중 승인 권고 + 사람 확인 없음 1건
        "reviewed_item_ratio": 0.0,
        "reason_code_counts": {},
        "deviation_by_item": [
            {"item_name": "수분", "fail_count": 1, "undetermined_count": 1},
            {"item_name": "Na", "fail_count": 1, "undetermined_count": 0},
        ],
    }


def test_admin_default_is_all(auth_client, docs, admin):
    auth_client.login_as(admin)
    data = auth_client.get(URL).json()["data"]
    assert data["total_processed"] == 4
    assert data["conditional_accept_count"] == 1
    assert data["pass_rate"] == 75.0
    assert data["recommendation_match_rate"] == 66.7  # 불합격 권고 → 조건부 승인은 불일치 (2/3)
    assert data["deviation_by_item"][0] == {"item_name": "수분", "fail_count": 2, "undetermined_count": 1}


def test_admin_scope_mine_and_user_filter(auth_client, docs, user, admin):
    auth_client.login_as(admin)
    assert auth_client.get(URL, params={"scope": "mine"}).json()["data"]["total_processed"] == 1
    assert auth_client.get(URL, params={"user_id": user.id}).json()["data"]["total_processed"] == 3


@pytest.mark.parametrize("params", [{"scope": "all"}, {"user_id": 1}])
def test_user_cannot_view_others(auth_client, docs, params):
    r = auth_client.get(URL, params=params)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_user_scope_mine_explicit(auth_client, docs):
    assert auth_client.get(URL, params={"scope": "mine"}).json()["data"]["total_processed"] == 3


def test_period_filter_uses_kst_approval_date(auth_client, docs, admin):
    auth_client.login_as(admin)
    on_9th = auth_client.get(URL, params={"from": "2026-10-09", "to": "2026-10-09"}).json()["data"]
    assert on_9th["total_processed"] == 1  # 10/8 업로드, 10/9 00:10 처분
    assert on_9th["on_hold_count"] == 0
    on_5th = auth_client.get(URL, params={"from": "2026-10-05", "to": "2026-10-05"}).json()["data"]
    assert (on_5th["total_processed"], on_5th["on_hold_count"]) == (3, 1)


def test_empty(auth_client, db):
    data = auth_client.get(URL).json()["data"]
    assert data["total_processed"] == 0
    assert data["pass_rate"] == 0.0
    assert data["avg_processing_time_sec"] == 0.0
    assert data["deviation_by_item"] == []


def test_invalid_scope(auth_client, db):
    r = auth_client.get(URL, params={"scope": "everyone"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_requires_login(client, db):
    assert client.get(URL).status_code == 401


# ---- v1.4안 지표 (auto_approve_rate, reviewed_item_ratio, reason_code_counts, material_code) ----
def item(name, judgement="pass", reason_code=None, reviewed=False, judgement_reason=None):
    return {"normalized_name": name, "judgement": judgement, "reason_code": reason_code, "reviewed": reviewed,
            "judgement_reason": judgement_reason}


@pytest.fixture
def v14_docs(db, user):
    # 정상(승인) 3건: 자동 1, 사람이 확인한 뒤 승인 권고 1, 보류 권고였는데 승인 1
    make_doc(db, user, S.APPROVED, R.APPROVE, D.ACCEPT, [item("Na"), item("Fe")])
    make_doc(db, user, S.APPROVED, R.APPROVE, D.ACCEPT, [item("Na", reviewed=True), item("Fe")])
    make_doc(db, user, S.APPROVED, R.HOLD, D.ACCEPT, [item("Fe", "check", "ND_NO_LOD")])
    # 조건부 승인은 정상 문서에서 제외
    make_doc(db, user, S.APPROVED, R.APPROVE, D.CONDITIONAL_ACCEPT, [item("Na")], material_code="LIOH")
    # 불합격
    make_doc(db, user, S.APPROVED, R.REJECT, D.REJECT,
             [item("Ca", "fail", "OUT_OF_SPEC"), item("K", "undetermined", "BOUND_ABOVE_LIMIT", reviewed=True)])


def test_auto_approve_rate_uses_normal_documents(auth_client, v14_docs):
    data = auth_client.get(URL).json()["data"]
    assert data["auto_approve_rate"] == 33.3        # 정상 3건 중 1건
    assert data["reviewed_item_ratio"] == 25.0      # 전체 항목 8개 중 사람 확인 2개
    assert data["reason_code_counts"] == {"BOUND_ABOVE_LIMIT": 1, "ND_NO_LOD": 1, "OUT_OF_SPEC": 1}


def test_material_code_filter(auth_client, v14_docs):
    lioh = auth_client.get(URL, params={"material_code": "LIOH"}).json()["data"]
    assert (lioh["total_processed"], lioh["conditional_accept_count"]) == (1, 1)
    assert lioh["auto_approve_rate"] == 0.0         # 정상(승인) 문서가 없음
    li2co3 = auth_client.get(URL, params={"material_code": "LI2CO3"}).json()["data"]
    assert li2co3["total_processed"] == 4
    assert auth_client.get(URL, params={"material_code": "NONE"}).json()["data"]["total_processed"] == 0


def test_reviewed_ratio_counts_all_items(auth_client, db, user):
    """분모: 전체 항목 (누락·참고 항목 포함)."""
    make_doc(db, user, S.APPROVED, R.HOLD, D.ACCEPT, [
        item("Na", reviewed=True),
        item("Fe"),
        item("황산염", "missing", "MISSING_REQUIRED", reviewed=True, judgement_reason="CoA에 항목 없음"),
        item("Mg", judgement_reason="규격 없음"),
        item("외관", judgement_reason="정성 항목, 판정 제외"),
    ])
    assert auth_client.get(URL).json()["data"]["reviewed_item_ratio"] == 40.0   # 5개 중 2개 (참고 2개 포함)
