"""[담당: 홍채령]"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.enums import DocumentStatus as S, FinalDecision as D, LotRecommendation as R
from app.models import Document, ExtractionResult

KST = ZoneInfo("Asia/Seoul")
URL = "/api/v1/dashboard/summary"


def make_doc(db, uploader, status, rec=None, decision=None, items=(), uploaded_at=None, minutes=10):
    """items: (항목명, 판정) 목록. 처분 일시는 업로드 minutes 분 뒤."""
    uploaded_at = uploaded_at or datetime(2026, 10, 5, 9, 0, tzinfo=KST)
    doc = Document(
        file_name="coa.pdf",
        file_path="x",
        file_size=1,
        content_type="application/pdf",
        material_code="LI2CO3",
        status=status,
        lot_recommendation=rec,
        final_decision=decision,
        uploaded_by=uploader.id,
        uploaded_at=uploaded_at,
        approved_by=uploader.id if status == S.APPROVED else None,
        approved_at=uploaded_at + timedelta(minutes=minutes) if status == S.APPROVED else None,
    )
    doc.extraction = ExtractionResult(
        result={"items": [{"normalized_name": n, "judgement": j} for n, j in items]}
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
