"""[담당: 고도영] LLM 서버 클라이언트 (llama.cpp llama-server 등 OpenAI 호환 /v1/chat/completions).

LLM 은 덧붙이는 기능이다. 서버가 없거나 느리거나 이상한 답을 주면 None 을 돌려주고,
부르는 쪽(정규화·의미 분류·문의 초안)은 규칙·템플릿으로 계속한다. 예외를 밖으로 내지 않는다.

- 연결 실패·시간 초과가 나면 DOWN_SECONDS 동안 묻지 않고 바로 None (항목마다 기다리지 않게)
- 같은 질문의 답은 기억한다 (온도 0 이라 답이 같다)
- for_document() 는 문서 1건용 복사본이다. 기억·꺼짐 상태는 같이 쓰고, 호출 수만 새로 센다
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

logger = logging.getLogger(__name__)

DOWN_SECONDS = 60     # 연결 실패 뒤 묻지 않는 시간
CACHE_SIZE = 2048     # 기억하는 답 수
DOC_MAX_CALLS = 12    # 문서 1건의 호출 상한 (CPU 에서 항목당 약 7초)
DRAFT_TIMEOUT = 180   # 문의 초안은 길어서 시간 제한을 따로 둔다 (CPU 약 38초)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class _Shared:
    """여러 스레드·문서가 같이 쓰는 상태."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cache: OrderedDict[str, object] = OrderedDict()
        self.down_until = 0.0


class LLMClient:
    def __init__(self, base_url: str, *, timeout: float = 60.0, max_calls: int | None = None,
                 _shared: _Shared | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_calls = max_calls
        self.calls = 0
        self._shared = _shared or _Shared()

    def for_document(self, max_calls: int = DOC_MAX_CALLS) -> LLMClient:
        return LLMClient(self.base_url, timeout=self.timeout, max_calls=max_calls, _shared=self._shared)

    # ------------------------------------------------------------------
    def json_chat(self, system: str, user: str, schema: dict, max_tokens: int = 128) -> dict | None:
        """JSON 틀(schema)로 답을 받아 dict 로. 실패하면 None."""
        fmt = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
        content = self._ask("json", system, user, max_tokens, fmt, self.timeout)
        if content is None:
            return None
        try:
            out = json.loads(_FENCE.sub("", content.strip()))
        except json.JSONDecodeError:
            logger.warning("LLM 답이 JSON 이 아님: %.80s", content)
            return None
        return out if isinstance(out, dict) else None

    def text_chat(self, system: str, user: str, max_tokens: int = 1500, timeout: float | None = None) -> str | None:
        """일반 글로 답을 받는다. 실패하면 None."""
        return self._ask("text", system, user, max_tokens, None, timeout or self.timeout)

    # ------------------------------------------------------------------
    def _ask(self, kind: str, system: str, user: str, max_tokens: int, fmt: dict | None,
             timeout: float) -> str | None:
        key = json.dumps([kind, system, user, fmt, max_tokens], ensure_ascii=False, sort_keys=True)
        shared = self._shared
        with shared.lock:
            if key in shared.cache:
                shared.cache.move_to_end(key)
                return shared.cache[key]
            if time.monotonic() < shared.down_until:
                return None
            if self.max_calls is not None and self.calls >= self.max_calls:
                return None
            self.calls += 1

        content = self._post(system, user, max_tokens, fmt, timeout)
        if content is not None:
            with shared.lock:
                shared.cache[key] = content
                while len(shared.cache) > CACHE_SIZE:
                    shared.cache.popitem(last=False)
        return content

    def _post(self, system: str, user: str, max_tokens: int, fmt: dict | None, timeout: float) -> str | None:
        body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if fmt:
            body["response_format"] = fmt
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            logger.warning("LLM 서버 오류 %s", e.code)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            with self._shared.lock:
                self._shared.down_until = time.monotonic() + DOWN_SECONDS
            logger.warning("LLM 서버에 연결할 수 없음(%s). %d초 동안 LLM 없이 진행", e, DOWN_SECONDS)
        except (ValueError, KeyError, IndexError, TypeError):
            logger.warning("LLM 서버 응답 형식이 다름")
        return None
