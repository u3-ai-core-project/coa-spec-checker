"""[담당: 장수민] 공통 응답·에러 형식 테스트 (명세 1장, 5장). DB 불필요."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.errors import AppException, ErrorCode
from app.main import app

_router = APIRouter(prefix="/_test")


class _Body(BaseModel):
    reason: str


@_router.get("/app-error")
def _app_error():
    raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)


@_router.get("/custom-message")
def _custom():
    raise AppException(ErrorCode.REASON_REQUIRED, "조건부 승인은 사유가 필요합니다")


@_router.get("/unauthorized")
def _unauth():
    raise AppException(ErrorCode.UNAUTHORIZED)


@_router.post("/validate")
def _validate(body: _Body):
    return body


@_router.get("/crash")
def _crash():
    raise RuntimeError("boom")


app.include_router(_router)


from app import __version__


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"success": True, "data": {"status": "ok", "database": "ok", "version": __version__}, "error": None}


def test_health_reports_db_failure(client, monkeypatch):
    """DB 연결이 끊기면 정상으로 보이지 않고 503 (운영 정책 4장)."""
    from app import main

    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr(main, "SessionLocal", broken)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DB_UNAVAILABLE"


def test_app_exception_uses_spec_format(client):
    r = client.get("/_test/app-error")
    assert r.status_code == 404
    assert r.json() == {
        "success": False,
        "data": None,
        "error": {"code": "DOCUMENT_NOT_FOUND", "message": "존재하지 않는 문서입니다"},
    }


def test_custom_message(client):
    r = client.get("/_test/custom-message")
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "REASON_REQUIRED", "message": "조건부 승인은 사유가 필요합니다"}


def test_401_has_bearer_header(client):
    r = client.get("/_test/unauthorized")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_validation_error_is_400(client):
    r = client.post("/_test/validate", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "reason" in r.json()["error"]["message"]


def test_unknown_path_is_404_in_spec_format(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_unhandled_exception_is_500(client):
    r = client.get("/_test/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"


def test_every_error_code_has_valid_status():
    for code in ErrorCode:
        # 429: 로그인 잠금 ACCOUNT_LOCKED, 507: 저장 공간 부족 STORAGE_FULL (운영 정책)
        assert code.status_code in {400, 401, 403, 404, 409, 422, 429, 500, 507}
