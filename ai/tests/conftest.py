"""[담당: 고도영] 테스트 공통 픽스처.

가상 CoA 3장(팀 제작)은 tests/fixtures 에 있다.
"""
from pathlib import Path

import pymupdf
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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
