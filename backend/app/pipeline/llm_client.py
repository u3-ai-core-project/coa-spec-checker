"""[담당: 고도영] LLM 서버 클라이언트 공유 (AI 추출기·AI 문의 초안이 같이 쓴다).

설정 LLM_BASE_URL 이 비어 있으면 None → LLM 없이 규칙·템플릿으로 동작한다.
주소마다 클라이언트 하나를 공유해서, 같은 질문의 답 기억과 '서버 꺼짐' 상태를 문서끼리 같이 쓴다.
"""
from functools import lru_cache

import coa_ai

from app.core.config import settings


def get_llm() -> coa_ai.LLMClient | None:
    return _client(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else None


@lru_cache
def _client(base_url: str) -> coa_ai.LLMClient:
    return coa_ai.LLMClient(base_url)
