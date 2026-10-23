"""테스트용 가짜 LLM 클라이언트 (LLMClient 와 같은 메서드). 정해 둔 답을 돌려주고 받은 질문을 기록한다.

json_answer / text_answer: 고정 답, 또는 (system, user, schema) 를 받아 답을 돌려주는 함수. None 이면 'LLM 없음'처럼 None.
"""
from __future__ import annotations


class FakeLLM:
    def __init__(self, json_answer=None, text_answer=None):
        self.json_answer = json_answer
        self.text_answer = text_answer
        self.calls: list[dict] = []
        self.documents = 0

    def for_document(self, max_calls: int = 12) -> FakeLLM:
        self.documents += 1
        return self

    def json_chat(self, system: str, user: str, schema: dict, max_tokens: int = 128) -> dict | None:
        self.calls.append({"system": system, "user": user, "schema": schema})
        a = self.json_answer
        return a(system, user, schema) if callable(a) else a

    def text_chat(self, system: str, user: str, max_tokens: int = 1500, timeout: float | None = None) -> str | None:
        self.calls.append({"system": system, "user": user, "schema": None})
        a = self.text_answer
        return a(system, user, None) if callable(a) else a
