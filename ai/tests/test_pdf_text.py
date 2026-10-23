"""[담당: 고도영] PDF 글자 → 줄·칸 후보, 첨자 복원"""
import pymupdf
import pytest

from coa_ai.pdf_text import PdfOpenError, phrases, read_pages


def _texts(path):
    return [ln.text for pg in read_pages(path) for ln in pg.lines]


def test_synthetic_a_restores_super_and_subscripts(fixture_pdf):
    texts = _texts(fixture_pdf("COA_A_0007.pdf"))
    assert any(t.startswith("Sulfate (SO₄²⁻)") for t in texts)
    assert any(t.startswith("Chloride (Cl⁻)") for t in texts)


def test_phrases_split_on_wide_gaps(fixture_pdf):
    page = read_pages(fixture_pdf("COA_A_0007.pdf"))[0]
    i, line = next((i, ln) for i, ln in enumerate(page.lines) if ln.text.startswith("Sodium (Na)"))
    assert [p.text for p in phrases(line, i)] == ["Sodium (Na)", "ICP-OES", "12.5 ppm", "≤ 50 ppm"]


def test_small_digits_become_subscripts(tmp_path):
    # Alfa 13418 처럼 'Li CO' 사이와 뒤에 작은 숫자가 기준선 아래에 따로 찍힌 경우
    doc = pymupdf.open()
    page = doc.new_page()
    x = 50
    for text, size, dy in [("Li", 12, 0), ("2", 8, 1.5), ("CO", 12, 0), ("3", 8, 1.5)]:
        page.insert_text((x, 100 + dy), text, fontsize=size)
        x += pymupdf.get_text_length(text, fontsize=size)
    page.insert_text((200, 100), "99.5 %", fontsize=12)
    path = tmp_path / "sub.pdf"
    doc.save(path)
    assert _texts(path) == ["Li₂CO₃ 99.5 %"]


def test_blank_pdf_has_no_lines(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    path = tmp_path / "blank.pdf"
    doc.save(path)
    pages = read_pages(path)
    assert len(pages) == 1 and pages[0].lines == []


def test_broken_file_raises(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nnot really a pdf")
    with pytest.raises(PdfOpenError):
        read_pages(path)
