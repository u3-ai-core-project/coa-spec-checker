"""[담당: 장수민] AI 추출기 인터페이스 — 고도영 파트 연결 지점.

AI 파트는 아래 Extractor 를 만족하는 클래스를 만들어 get_extractor() 에 등록하면 된다.
입력은 저장된 원본 파일 경로, 원자재 구분, 업로드 파일 이름, 출력은 app.schemas.extraction.ExtractionInput.
추출에 실패하면 ExtractionError(사용자에게 보여줄 사유) 를 던진다.
"""
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.schemas.extraction import ExtractionInput


class ExtractionError(Exception):
    """추출 실패. 메시지는 documents.error_message 에 그대로 저장되어 화면에 표시된다."""


class Extractor(Protocol):
    def extract(self, file_path: Path, *, material_code: str, original_name: str | None = None) -> ExtractionInput:
        """file_path: 서버에 저장된 파일(이름은 문서 ID), original_name: 사용자가 올린 파일 이름"""
        ...


def get_extractor() -> Extractor:
    if settings.EXTRACTOR == "mock":
        from app.pipeline.mock_extractor import MockExtractor

        return MockExtractor(Path(settings.MOCK_EXTRACTION_DIR))
    if settings.EXTRACTOR == "ai":
        from app.pipeline.ai_extractor import AIExtractor  # ai/ 패키지(coa_ai)가 설치돼 있어야 한다

        return AIExtractor()
    raise ValueError(f"알 수 없는 EXTRACTOR 설정: {settings.EXTRACTOR}")
