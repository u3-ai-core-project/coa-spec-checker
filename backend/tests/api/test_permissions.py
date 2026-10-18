"""[담당: 홍채령] USER로 관리자 기능 접근 시 403, 토큰 없음·만료·위조 401"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import settings
from app.core.enums import SpecType
from app.core.security import create_access_token
from app.models import SpecItem, SpecSet


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def assert_unauthorized(r):
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert r.headers["www-authenticate"] == "Bearer"


def test_no_token(client, db):
    assert_unauthorized(client.get("/api/v1/auth/me"))


def test_expired_token(client, user):
    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


def test_forged_token(client, user):
    token = jwt.encode({"sub": str(user.id)}, "not-the-server-secret", algorithm=settings.JWT_ALGORITHM)
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


@pytest.mark.parametrize("token", ["garbage", "a.b.c"])
def test_malformed_token(client, db, token):
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


def test_token_of_deleted_user(client, user, db):
    token = create_access_token(user.id)
    db.delete(user)
    db.commit()
    assert_unauthorized(client.get("/api/v1/auth/me", headers=bearer(token)))


def test_user_cannot_list_users(client, user):
    r = client.get("/api/v1/users", headers=bearer(create_access_token(user.id)))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_admin_lists_users(client, user, admin):
    r = client.get("/api/v1/users", headers=bearer(create_access_token(admin.id)))
    assert r.status_code == 200
    assert r.json()["data"] == [
        {"id": user.id, "name": "김사용", "role": "USER"},
        {"id": admin.id, "name": "관리자", "role": "ADMIN"},
    ]


def test_user_token_works_on_other_api(client, user, db):
    """장수민 쪽 API 도 실제 토큰으로 통과하는지 (의존성 오버라이드 없이)."""
    r = client.get("/api/v1/documents", headers=bearer(create_access_token(user.id)))
    assert r.status_code == 200


# ---- 처분·규격 API 권한 (업무 분담 '권한 테스트', 실제 토큰·의존성 오버라이드 없이) ------------
# 처분 취소 403·USER 승인은 장수민 님 test_approval.test_real_token_permissions, 규격 수정 403(오버라이드)은
# test_specs.test_update_forbidden_for_user 에도 있다. 여기서는 빠진 조합을 실제 토큰으로 확인한다.
PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


def _row(name, raw_value):
    return {"raw_name": name, "normalized_name": name, "mapping_source": "dictionary",
            "raw_value": raw_value, "unit": "ppm", "confidence": 0.95}


# 로트 권고별 목업 추출 결과 (실제 CoA 아님). 규격: Na ≤ 50, Fe ≤ 5 ppm
MOCKS = {
    "approve": [_row("Na", "12"), _row("Fe", "1")],
    "reject": [_row("Na", "80"), _row("Fe", "1")],
    "hold": [_row("Na", "12"), _row("Fe", "none detected")],
}


@pytest.fixture
def spec_na(db) -> SpecItem:
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=SpecType.QUANTITATIVE),
                      SpecItem(item_name="Fe", unit="ppm", usl=5, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    return spec_set.items[0]


@pytest.fixture
def upload(client, user, spec_na, tmp_path, monkeypatch):
    """USER 토큰으로 업로드한 문서 id. 추출은 BackgroundTasks 로 응답 직후 끝난다."""
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    for name, items in MOCKS.items():
        (mock_dir / f"{name}.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _upload(kind: str) -> str:
        r = client.post("/api/v1/documents", files={"file": (f"{kind}.pdf", PDF)},
                        data={"material_code": "LI2CO3"}, headers=bearer(create_access_token(user.id)))
        assert r.status_code == 201
        return r.json()["data"]["document_id"]
    return _upload


def assert_forbidden(r):
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("kind, decision, reason", [
    ("approve", "accept", None),
    ("reject", "conditional_accept", "조건부 사용"),
    ("reject", "reject", None),
])
def test_user_can_dispose(client, user, upload, kind, decision, reason):
    """USER 도 최종 처분(승인·조건부 승인·불합격)을 할 수 있다 (명세 2.8)."""
    doc_id = upload(kind)
    r = client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": decision, "reason": reason},
                    headers=bearer(create_access_token(user.id)))
    assert r.status_code == 200
    assert (r.json()["data"]["status"], r.json()["data"]["final_decision"]) == ("approved", decision)


def test_user_can_hold(client, user, upload):
    doc_id = upload("hold")
    r = client.post(f"/api/v1/documents/{doc_id}/hold",
                    json={"follow_up": "request_detection_limit", "reason": "검출한계 요청"},
                    headers=bearer(create_access_token(user.id)))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "on_hold"


def test_user_cannot_update_spec(client, user, admin, spec_na):
    r = client.patch(f"/api/v1/specs/{spec_na.id}", json={"usl": 40}, headers=bearer(create_access_token(user.id)))
    assert_forbidden(r)
    r = client.patch(f"/api/v1/specs/{spec_na.id}", json={"usl": 40}, headers=bearer(create_access_token(admin.id)))
    assert r.status_code == 200


@pytest.mark.parametrize("params", [{"scope": "all"}, {"user_id": 1}])
def test_user_cannot_view_all_dashboard(client, user, params):
    assert_forbidden(client.get("/api/v1/dashboard/summary", params=params,
                                headers=bearer(create_access_token(user.id))))


def test_admin_views_all_dashboard(client, user, admin):
    for params in ({"scope": "all"}, {"user_id": user.id}):
        r = client.get("/api/v1/dashboard/summary", params=params, headers=bearer(create_access_token(admin.id)))
        assert r.status_code == 200


@pytest.mark.parametrize("method, path, body", [
    ("get", "/api/v1/documents", None),
    ("get", "/api/v1/users", None),
    ("get", "/api/v1/dashboard/summary", None),
    ("get", "/api/v1/specs", None),
    ("patch", "/api/v1/specs/1", {"usl": 1}),
    ("post", "/api/v1/documents/x/approve", {"decision": "accept"}),
    ("post", "/api/v1/documents/x/hold", {"follow_up": "other", "reason": "x"}),
    ("post", "/api/v1/documents/x/cancel-approval", {"reason": "x"}),
])
def test_protected_endpoints_require_token(client, db, method, path, body):
    """로그인 API 외에는 모두 토큰이 필요하다 (명세 1장). 문서·규격 존재 여부보다 인증을 먼저 본다."""
    kwargs = {"json": body} if body is not None else {}
    assert_unauthorized(getattr(client, method)(path, **kwargs))
    forged = jwt.encode({"sub": "1"}, "not-the-server-secret", algorithm=settings.JWT_ALGORITHM)
    assert_unauthorized(getattr(client, method)(path, headers=bearer(forged), **kwargs))
