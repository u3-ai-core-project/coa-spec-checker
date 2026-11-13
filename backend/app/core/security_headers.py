"""[담당: 홍채령] API 응답 보안 헤더 (운영 정책 2장: "화면 보안 정책(CSP)과 사용 부품 점검을 적용").

로그인 토큰은 브라우저 localStorage 에 그대로 둔다 (정책). 그래서 스크립트 끼워 넣기(XSS)를 줄이는 것이 중요하다.
화면(프론트) 쪽 CSP 는 프론트 서버가 붙이고, 여기서는 API 응답에 붙인다.
API 응답은 JSON·파일뿐이라 브라우저가 그 안에서 스크립트·스타일·그림을 불러올 일이 없으므로 가장 엄격하게 잠근다.

- Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'
  응답을 HTML 처럼 열어도 아무것도 실행·로드하지 못하고, 다른 사이트가 iframe 으로 감쌀 수 없다
- X-Content-Type-Options: nosniff     브라우저가 파일 종류를 멋대로 추측하지 않게 (예: PDF 를 HTML 로 실행)
- X-Frame-Options: DENY               frame-ancestors 를 모르는 옛 브라우저용 같은 뜻
- Referrer-Policy: no-referrer         API 주소(문서 ID 포함)를 다른 곳에 넘기지 않게

원본 보기(GET /documents/{id}/file): 프론트는 fetch 로 받아 blob 으로 바꾼 뒤 react-pdf 로 그린다 (iframe 아님).
그래서 frame-ancestors 'none' 이어도 화면이 깨지지 않는다. 이 주소는 토큰(Authorization 헤더)이 있어야 열려
브라우저 주소창이나 iframe 으로 직접 여는 방식은 원래 쓸 수 없다.

/docs, /redoc (API 문서 화면): CDN 에서 스크립트를 받고 페이지 안에 스크립트가 있어 엄격한 CSP 로는 열리지 않는다.
이 두 주소만 CSP 를 붙이지 않는다 (나머지 헤더는 붙인다). 운영에서 문서 화면을 닫으려면 FastAPI(docs_url=None) 로 끈다.

SECURITY_HEADERS_ENABLED=false 로 모두 끌 수 있다 (문제 확인용). 앱이 이미 넣은 같은 이름 헤더는 덮어쓰지 않는다.
"""
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_PATHS = ("/docs", "/redoc")  # /docs/oauth2-redirect 포함

COMMON_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def headers_for(path: str) -> dict[str, str]:
    headers = dict(COMMON_HEADERS)
    if not any(path == p or path.startswith(p + "/") for p in DOCS_PATHS):
        headers["Content-Security-Policy"] = API_CSP
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.SECURITY_HEADERS_ENABLED:
            await self.app(scope, receive, send)
            return
        extra = headers_for(scope["path"])

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in extra.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
