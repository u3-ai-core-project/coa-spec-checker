"""[담당: 고도영] AI 추출기 어댑터 (DB 불필요). ai/ 패키지가 설치돼 있지 않으면 건너뛴다."""
from pathlib import Path

import pytest

pytest.importorskip("coa_ai")

from app.core.config import settings  # noqa: E402
from app.pipeline.ai_extractor import AIExtractor  # noqa: E402
from app.pipeline.extractor import ExtractionError, get_extractor  # noqa: E402
from app.schemas.extraction import ExtractionInput  # noqa: E402

FIXTURES = Path(__file__).parents[3] / "ai" / "tests" / "fixtures"


@pytest.fixture
def extractor(monkeypatch):
    monkeypatch.setattr(AIExtractor, "load_mappings", staticmethod(lambda material_code: {}))
    return AIExtractor()


def test_get_extractor_ai(monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTOR", "ai")
    assert isinstance(get_extractor(), AIExtractor)


def test_extract_returns_extraction_input(extractor):
    result = extractor.extract(FIXTURES / "COA_A_0007.pdf", material_code="LIOH", original_name="COA_A_0007.pdf")
    assert isinstance(result, ExtractionInput)
    assert (result.lot_no, result.supplier, len(result.items)) == ("SL25-0008", "Selmora Lithium S.A.", 15)
    co3 = next(i for i in result.items if i.normalized_name == "탄산")
    assert (co3.raw_value, co3.raw_spec, co3.mapping_source, co3.confidence) == ("0.36 %", "≤ 0.40 %", "dictionary", 0.95)
    assert co3.bbox is not None and co3.bbox.page == 1


def test_db_mappings_are_passed(monkeypatch):
    monkeypatch.setattr(AIExtractor, "load_mappings", staticmethod(lambda material_code: {"Sodium (Na)": "나트륨"}))
    result = AIExtractor().extract(FIXTURES / "COA_A_0007.pdf", material_code="LIOH")
    assert "나트륨" in {i.normalized_name for i in result.items}


def test_failure_becomes_extraction_error(extractor, tmp_path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ExtractionError, match="이미지 파일을 열 수 없습니다"):
        extractor.extract(image, material_code="LIOH")


@pytest.mark.parametrize("url, has_llm", [(None, False), ("http://127.0.0.1:9", True)])
def test_llm_client_is_passed(extractor, monkeypatch, url, has_llm):
    import coa_ai

    captured = {}

    def fake_extract(path, **kwargs):
        captured.update(kwargs)
        raise coa_ai.ExtractionFailed("확인용")

    monkeypatch.setattr(settings, "LLM_BASE_URL", url)
    monkeypatch.setattr(coa_ai, "extract", fake_extract)
    with pytest.raises(ExtractionError):
        extractor.extract(FIXTURES / "COA_A_0007.pdf", material_code="LIOH")
    assert isinstance(captured["llm"], coa_ai.LLMClient) is has_llm
