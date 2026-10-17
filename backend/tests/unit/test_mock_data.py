"""[담당: 고도영] 목업 추출 데이터(mock_data/*.json)가 AI 추출 계약(ExtractionInput)에 맞는지."""
import json
from pathlib import Path

import pytest

from app.schemas.extraction import ExtractionInput

MOCK_DIR = Path(__file__).parents[2] / "app" / "pipeline" / "mock_data"


@pytest.mark.parametrize("path", sorted(MOCK_DIR.glob("*.json")), ids=lambda p: p.name)
def test_mock_data_matches_extraction_input(path):
    data = ExtractionInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert data.items
