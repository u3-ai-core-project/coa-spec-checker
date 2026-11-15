"""[담당: 홍채령] 로그에 문서 내용·개인정보를 남기지 않기 테스트 (운영 정책 3장, app/core/safe_log.py)."""
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core import safe_log
from app.core.config import settings
from app.main import app

SECRET = "Na 80ppm 김검수 Bearer abc.def"  # 예외 메시지에 섞일 수 있는 문서 값·이름·토큰


def _raise():
    raise ValueError(SECRET)


def test_default_logs_type_and_location_only(caplog, monkeypatch):
    monkeypatch.setattr(settings, "LOG_DEBUG_DETAIL", False)
    logger = logging.getLogger("t.safe")
    with caplog.at_level(logging.ERROR, logger="t.safe"):
        try:
            _raise()
        except ValueError as e:
            safe_log.log_exception(logger, "문서 추출 실패: %s", "doc-1", exc=e)
    assert "문서 추출 실패: doc-1 [ValueError at " in caplog.text
    assert "test_safe_log.py:" in caplog.text
    assert SECRET not in caplog.text
    assert caplog.records[0].exc_info is None  # traceback 도 남기지 않는다


def test_cause_type_only(caplog, monkeypatch):
    monkeypatch.setattr(settings, "LOG_DEBUG_DETAIL", False)
    logger = logging.getLogger("t.safe")
    with caplog.at_level(logging.ERROR, logger="t.safe"):
        try:
            try:
                _raise()
            except ValueError as e:
                raise RuntimeError("wrap " + SECRET) from e
        except RuntimeError as e:
            safe_log.log_exception(logger, "실패", exc=e)
    assert "RuntimeError at" in caplog.text and "(원인: ValueError)" in caplog.text
    assert SECRET not in caplog.text


def test_debug_detail_keeps_traceback(caplog, monkeypatch):
    monkeypatch.setattr(settings, "LOG_DEBUG_DETAIL", True)
    logger = logging.getLogger("t.safe")
    with caplog.at_level(logging.ERROR, logger="t.safe"):
        try:
            _raise()
        except ValueError as e:
            safe_log.log_exception(logger, "실패", exc=e)
    assert caplog.records[0].exc_info is not None
    assert SECRET in caplog.text  # 개발 환경에서만 켜는 이유


def test_username_tag_stable_and_hides_name():
    tag = safe_log.username_tag("Kim ")
    assert tag == safe_log.username_tag("kim") and tag.startswith("u-") and len(tag) == 10
    assert "kim" not in tag
    assert tag != safe_log.username_tag("lee")


# ---- 예상 못 한 예외: 사용자에게는 일반 문구만, 로그에는 종류·위치만 ----------------------
_router = APIRouter()


@_router.get("/__test_boom")
def _boom():
    raise ValueError(SECRET)


@pytest.fixture
def boom_client():
    app.include_router(_router)
    yield TestClient(app, raise_server_exceptions=False)
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/__test_boom"]


def test_unhandled_error_hides_details(boom_client, caplog, monkeypatch):
    monkeypatch.setattr(settings, "LOG_DEBUG_DETAIL", False)
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        r = boom_client.get("/__test_boom", headers={"Authorization": "Bearer secret-token-xyz"})
    assert r.status_code == 500
    assert r.json()["error"] == {"code": "INTERNAL_ERROR", "message": "서버 오류가 발생했습니다"}
    assert SECRET not in r.text
    assert "처리하지 못한 오류: GET /__test_boom [ValueError at" in caplog.text
    assert SECRET not in caplog.text and "secret-token-xyz" not in caplog.text
