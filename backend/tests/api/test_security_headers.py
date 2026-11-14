"""[담당: 홍채령] API 보안 헤더 테스트 (운영 정책 2장, app/core/security_headers.py). DB 필요 없는 것 위주."""
import pytest

from app.core.config import settings
from app.core.security_headers import API_CSP

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


def assert_secure(r, *, csp=True):
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    if csp:
        assert r.headers["content-security-policy"] == API_CSP
    else:
        assert "content-security-policy" not in r.headers


def test_json_and_error_responses_have_headers(client):
    assert_secure(client.get("/api/v1/auth/me"))              # 401
    assert_secure(client.get("/api/v1/no-such-path"))         # 404
    assert_secure(client.get("/openapi.json"))


def test_preflight_has_headers(client):
    r = client.options("/api/v1/documents", headers={"Origin": settings.CORS_ORIGINS[0],
                                                     "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200
    assert_secure(r)


def test_too_large_has_headers(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_KB", 1)
    r = client.post("/api/v1/auth/login", content=b"0" * 4096, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert_secure(r)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_docs_pages_still_work(client, path):
    """API 문서 화면은 CDN 스크립트·페이지 안 스크립트를 써서 CSP 를 붙이지 않는다 (나머지 헤더는 붙인다)."""
    r = client.get(path)
    assert r.status_code == 200
    assert_secure(r, csp=False)


def test_can_disable(client, monkeypatch):
    monkeypatch.setattr(settings, "SECURITY_HEADERS_ENABLED", False)
    r = client.get("/api/v1/auth/me")
    assert "content-security-policy" not in r.headers and "x-frame-options" not in r.headers


def test_file_and_report_downloads_have_headers(auth_client, db):
    """원본 파일·엑셀도 같은 헤더. 프론트는 fetch → blob 으로 보여 주므로 frame-ancestors 'none' 이어도 괜찮다."""
    from seeds.seed_specs import seed_specs
    seed_specs(db)
    db.commit()
    r = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)}, data={"material_code": "LI2CO3"})
    doc_id = r.json()["data"]["document_id"]
    f = auth_client.get(f"/api/v1/documents/{doc_id}/file")
    assert f.status_code == 200 and f.content == PDF
    assert f.headers["content-type"] == "application/pdf"
    assert_secure(f)
