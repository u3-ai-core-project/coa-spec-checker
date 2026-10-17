"""[담당: 고도영] 테스트 공통 픽스처.

가상 CoA 3장(팀 제작)은 tests/fixtures 에 있다.
실물 CoA 는 라이선스 문제로 저장소에 넣지 않으므로 COA_REAL_DIR 로 폴더를 지정했을 때만 실물 테스트를 돈다.
"""
import os
from pathlib import Path

import pymupdf
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REAL_DIR = Path(os.environ.get("COA_REAL_DIR", Path(__file__).parents[1] / "data" / "raw" / "real"))


@pytest.fixture
def fixture_pdf():
    return lambda name: FIXTURES / name


@pytest.fixture
def make_pdf(tmp_path):
    """글줄 목록으로 1쪽짜리 텍스트 PDF 를 만든다. 각 줄은 [(x, 글), ...] 또는 글 하나."""
    def make(lines, name="doc.pdf", line_height=16):
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        y = 60
        for line in lines:
            parts = [(50, line)] if isinstance(line, str) else line
            for x, text in parts:
                page.insert_text((x, y), text, fontsize=9)
            y += line_height
        path = tmp_path / name
        doc.save(path)
        doc.close()
        return path
    return make


@pytest.fixture
def real_pdf():
    def get(prefix: str) -> Path:
        if not REAL_DIR.is_dir():
            pytest.skip(f"실물 CoA 폴더 없음: {REAL_DIR}")
        found = sorted(REAL_DIR.glob(f"{prefix}*.pdf"))
        if not found:
            pytest.skip(f"실물 CoA 없음: {prefix}")
        return found[0]
    return get
