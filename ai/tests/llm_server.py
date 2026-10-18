"""테스트용 가짜 LLM 서버 (OpenAI 호환 /v1/chat/completions). 실제 HTTP 로 주고받는다.

replies 원소: 답 글(str), ("sleep", 초) 는 그만큼 기다린 뒤 "{}", ("status", 코드) 는 그 HTTP 오류.
replies 가 함수면 요청 본문(dict)을 받아 위 원소 하나를 돌려준다. 목록을 다 쓰면 마지막 원소를 되풀이한다.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLMServer:
    def __init__(self, replies):
        self.replies = replies
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                reply = server._next(body)
                if isinstance(reply, tuple) and reply[0] == "status":
                    self.send_response(reply[1])
                    self.end_headers()
                    return
                if isinstance(reply, tuple) and reply[0] == "sleep":
                    time.sleep(reply[1])
                    reply = "{}"
                data = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}]}).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 클라이언트가 시간 초과로 먼저 끊음

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def _next(self, body: dict):
        with self._lock:
            self.requests.append(body)
            if callable(self.replies):
                return self.replies(body)
            n = len(self.requests) - 1
            return self.replies[min(n, len(self.replies) - 1)]

    def __enter__(self) -> FakeLLMServer:
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
