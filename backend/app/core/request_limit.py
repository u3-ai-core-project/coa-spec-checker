"""[담당: 홍채령] 요청 전체 크기 상한 (운영 정책 3장).

"파일 크기는 읽는 도중에 확인해 20MB를 넘으면 즉시 중단하고, 요청 전체 크기 상한도 둔다."

파일 하나 상한(MAX_UPLOAD_MB)은 documents.py 의 _read_limited 가 본다. 그런데 FastAPI 는 업로드 함수를 부르기 전에
요청 본문(멀티파트)을 먼저 끝까지 받아 임시 파일에 쓴다. 그래서 아주 큰 요청은 함수에 닿기 전에 막아야 한다.
이 미들웨어가 모든 요청의 본문 크기를 맨 앞에서 본다.

- 업로드 (POST /api/v1/documents): MAX_UPLOAD_MB + UPLOAD_FORM_OVERHEAD_KB
- 일괄 접수 (POST /api/v1/documents/batch): MAX_UPLOAD_MB × (MAX_BATCH_FILES + 1) + UPLOAD_FORM_OVERHEAD_KB
  (+1 은 입고 정보 CSV. CSV 도 파일 하나 상한까지 받는다)
- 그 밖의 모든 요청: MAX_REQUEST_KB (기본 1MB). JSON 본문은 이보다 훨씬 작다

넘으면 413 REQUEST_TOO_LARGE (공통 에러 형식).

두 가지 경우를 모두 막는다.
1. Content-Length 헤더가 있는 요청 (브라우저 업로드는 거의 다 이렇다): 본문을 한 바이트도 읽기 전에 헤더만 보고 거절
2. Content-Length 가 없는 요청 (Transfer-Encoding: chunked 로 조금씩 보내는 경우): 크기를 미리 알 수 없으므로
   받는 대로 바이트를 세다가, 상한을 넘는 조각이 오는 순간 더 읽지 않고 413 으로 끝낸다.
   그래서 이런 요청도 서버가 받는 양은 "상한 + 마지막 조각 1개"를 넘지 않는다.
   (헤더에 적은 크기보다 실제로 더 보내는 요청도 같은 방법으로 센다)
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.errors import ErrorCode, error_response

KB = 1024
MB = 1024 * 1024

UPLOAD_PATH = "/api/v1/documents"
BATCH_PATH = "/api/v1/documents/batch"


def limit_for(method: str, path: str) -> int:
    """이 요청 본문에 허용하는 최대 바이트."""
    path = path.rstrip("/") or "/"
    overhead = settings.UPLOAD_FORM_OVERHEAD_KB * KB
    per_file = settings.MAX_UPLOAD_MB * MB
    if method == "POST" and path == UPLOAD_PATH:
        return per_file + overhead
    if method == "POST" and path == BATCH_PATH:
        return per_file * (settings.MAX_BATCH_FILES + 1) + overhead
    return settings.MAX_REQUEST_KB * KB


def _message(limit: int) -> str:
    size = f"{limit / MB:.0f}MB" if limit >= MB else f"{limit // KB}KB"
    return f"요청 크기가 너무 큽니다 (최대 {size})"


class _TooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    """순수 ASGI 미들웨어. 본문을 메모리에 모으지 않고 지나가는 조각의 크기만 센다."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = limit_for(scope["method"], scope["path"])
        declared = _content_length(scope)
        if declared == -1:
            await error_response(ErrorCode.VALIDATION_ERROR, "Content-Length 헤더가 올바르지 않습니다")(scope, receive, send)
            return
        if declared is not None and declared > limit:
            await _reject(limit, scope, receive, send)
            return

        received = 0
        exceeded = False
        started = False  # 응답 시작(상태 코드)을 이미 보냈는지

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _TooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded and not started:
                # 앱이 본문 오류를 다른 응답(400 등)으로 바꿔 보내려 해도 413 으로 바꾼다
                if message["type"] == "http.response.start":
                    started = True
                    await _reject(limit, scope, receive, send)
                return
            if exceeded:
                return  # 이미 413 을 보냈다. 앱이 보내는 나머지는 버린다
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
            # 상한을 넘어 읽기를 멈춘 탓에 생긴 예외. 서버 오류가 아니라 413 이다
            if not started:
                started = True
                await _reject(limit, scope, receive, send)


def _content_length(scope: Scope) -> int | None:
    """Content-Length 값. 없으면 None, 숫자가 아니면 -1."""
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            text = value.decode("latin-1").strip()
            return int(text) if text.isdigit() else -1
    return None


async def _reject(limit: int, scope: Scope, receive: Receive, send: Send) -> None:
    response = error_response(ErrorCode.REQUEST_TOO_LARGE, _message(limit))
    response.headers["Connection"] = "close"  # 남은 본문을 더 받지 않고 연결을 끊게 한다
    await response(scope, receive, send)
