"""[담당: 고도영] AI 추출기 어댑터 — ai/ 의 coa_ai 패키지를 Extractor 인터페이스에 연결한다.

사용: backend 가상환경에서 `pip install -e ../ai` 후 .env 에 EXTRACTOR=ai
매핑 사전(item_mappings)은 문서마다 DB 에서 읽어 넘긴다. 담당자가 항목명을 고치면(source=manual) 다음 문서부터 반영된다.
"""
from pathlib import Path

import coa_ai
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ItemMapping
from app.pipeline.extractor import ExtractionError
from app.schemas.extraction import ExtractionInput


class AIExtractor:
    def extract(self, file_path: Path, *, material_code: str, original_name: str | None = None) -> ExtractionInput:
        try:
            result = coa_ai.extract(file_path, material_code=material_code, mappings=self.load_mappings(material_code))
        except coa_ai.ExtractionFailed as e:
            raise ExtractionError(str(e)) from e
        return ExtractionInput.model_validate(result.to_dict())

    @staticmethod
    def load_mappings(material_code: str) -> dict[str, str]:
        """{원문 항목명: 표준 항목명}. 시드(seed)와 담당자 수정(manual)을 모두 쓴다."""
        with SessionLocal() as db:
            rows = db.execute(
                select(ItemMapping.raw_name, ItemMapping.normalized_name).where(ItemMapping.material_code == material_code)
            ).all()
        return {r.raw_name: r.normalized_name for r in rows}
