"""[담당: 홍채령] 요청 전체 크기 상한 테스트 (운영 정책 3장, app/core/request_limit.py).

- Content-Length 가 상한보다 크면 본문을 읽기 전에 413 REQUEST_TOO_LARGE
- Content-Length 없이(chunked) 보내도 받은 양을 세다가 넘으면 413
"""
import asyncio

import pytest

from app.core.config import settings
from app.core.request_limit import BATCH_PATH, KB, MB, UPLOAD_PATH, RequestSizeLimitMiddleware, limit_for


def error(r):
    return r.status_code, r.json()["error"]["code"]


@pytest.fixture
def small(monkeypatch):
    """상한을 작게: 파일 1MB, 여유 16KB, 일반 요청 4KB, 일괄 2개."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    monkeypatch.setattr(settings, "UPLOAD_FORM_OVERHEAD_KB", 16)
    monkeypatch.setattr(settings, "MAX_REQUEST_KB", 4)
    monkeypatch.setattr(settings, "MAX_BATCH_FILES", 2)


def test_limit_for(small):
    assert limit_for("POST", UPLOAD_PATH) == MB + 16 * KB
    assert limit_for("POST", UPLOAD_PATH + "/") == MB + 16 * KB
    assert limit_for("POST", BATCH_PATH) == MB * 3 + 16 * KB          # 파일 2개 + 입고 CSV 1개
    assert limit_for("PATCH", "/api/v1/documents/x/extraction/1") == 4 * KB
    assert limit_for("GET", UPLOAD_PATH) == 4 * KB                    # 업로드 상한은 POST 만


def test_upload_over_limit_rejected_by_content_length(client, small):
    r = client.post(UPLOAD_PATH, content=b"0" * (MB + 17 * KB),
                    headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert error(r) == (413, "REQUEST_TOO_LARGE")
    assert "최대 1MB" in r.json()["error"]["message"]


def test_batch_over_limit_rejected(client, small):
    r = client.post(BATCH_PATH, content=b"0" * (3 * MB + 17 * KB),
                    headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert error(r) == (413, "REQUEST_TOO_LARGE")


def test_json_over_limit_rejected_before_auth(client, small):
    """인증보다 먼저 본다 (토큰 없이 큰 본문을 보내도 서버가 다 받지 않는다)."""
    r = client.post("/api/v1/auth/login", json={"username": "a" * 5000, "password": "x"})
    assert error(r) == (413, "REQUEST_TOO_LARGE")
    assert r.json()["error"]["message"] == "요청 크기가 너무 큽니다 (최대 4KB)"


def test_json_under_limit_passes(client, small):
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code != 413


def test_invalid_content_length_rejected(small):
    status, _ = _run_middleware([b"abc"], headers=[(b"content-length", b"12x")])
    assert status == 400


def test_chunked_body_over_limit_rejected_through_app(client, small):
    """httpx 는 생성기 본문을 Content-Length 없이(chunked) 보낸다."""
    def chunks():
        for _ in range(10):
            yield b"0" * KB

    r = client.post("/api/v1/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert error(r) == (413, "REQUEST_TOO_LARGE")


# ---- 미들웨어만 따로 (Content-Length 없는 요청을 정확히 흉내) ------------------------
def _run_middleware(chunks: list[bytes], headers=None, path="/api/v1/x", method="POST"):
    """조각(chunks)을 하나씩 보내는 가짜 클라이언트. (응답 상태, 앱이 읽은 조각 수)."""
    read = {"n": 0}

    async def app(scope, receive, send):
        while True:
            message = await receive()
            read["n"] += 1
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
    asyncio.run(RequestSizeLimitMiddleware(app)(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, read["n"]


def test_chunked_stops_reading_once_over_limit(small):
    """4KB 상한: 1KB 조각 100개를 보내도 5번째 조각에서 멈춘다 (나머지 95개는 받지 않음)."""
    status, reads = _run_middleware([b"0" * KB] * 100)
    assert status == 413
    assert reads == 4  # 앱에 넘긴 조각은 상한 안의 4개뿐


def test_chunked_under_limit_passes(small):
    status, reads = _run_middleware([b"0" * KB] * 4)
    assert (status, reads) == (200, 4)


def test_content_length_over_limit_reads_nothing(small):
    status, reads = _run_middleware([b"0" * KB], headers=[(b"content-length", str(10 * KB).encode())])
    assert (status, reads) == (413, 0)
