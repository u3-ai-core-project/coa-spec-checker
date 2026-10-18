"""[담당: 고도영] extract() 전체 흐름과 결과 형식 (backend ExtractionInput 과 같은 형식)"""
import io
import math
import re

import pymupdf
import pytest
from PIL import Image

from coa_ai import ExtractionFailed, extract
from coa_ai.models import Box, RawRow
from coa_ai.pipeline import MSG_BROKEN, MSG_BROKEN_IMAGE, MSG_NO_TEXT, MSG_NOT_COA, OCR_CONFIDENCE_CAP

INPUT_FIELDS = {"supplier", "lot_no", "test_date", "origin", "applied_standard", "items"}
ITEM_FIELDS = {"raw_name", "normalized_name", "mapping_source", "raw_value", "raw_spec", "unit", "confidence", "bbox"}


def test_synthetic_a(fixture_pdf):
    r = extract(fixture_pdf("COA_A_0007.pdf"), material_code="LIOH")
    assert (r.doc_type, r.lot_no, len(r.items)) == ("coa", "SL25-0008", 15)
    co3 = next(i for i in r.items if i.normalized_name == "탄산")
    assert (co3.raw_name, co3.raw_value, co3.raw_spec, co3.unit, co3.mapping_source, co3.confidence) == \
        ("Carbonate (as CO₃)", "0.36 %", "≤ 0.40 %", None, "dictionary", 0.95)
    assert co3.bbox["page"] == 1 and all(0 <= co3.bbox[k] <= 1 for k in "xywh")


@pytest.mark.parametrize("name, count", [("COA_A_0007.pdf", 15), ("COA_B_0005.pdf", 17), ("COA_D_0007.pdf", 20)])
def test_synthetic_all_items_mapped(fixture_pdf, name, count):
    r = extract(fixture_pdf(name), material_code="LIOH")
    assert len(r.items) == count
    assert all(i.mapping_source == "dictionary" and i.confidence >= 0.8 for i in r.items)


def test_to_dict_matches_backend_schema(fixture_pdf):
    d = extract(fixture_pdf("COA_D_0007.pdf"), material_code="LIOH").to_dict()
    assert INPUT_FIELDS <= set(d)
    assert set(d["items"][0]) == ITEM_FIELDS
    assert set(d["items"][0]["bbox"]) == {"page", "x", "y", "w", "h"}
    assert d["test_date"] == "2026-03-05"


def test_db_mappings_are_used(fixture_pdf):
    r = extract(fixture_pdf("COA_A_0007.pdf"), material_code="LIOH", mappings={"Sodium (Na)": "나트륨"})
    assert "나트륨" in {i.normalized_name for i in r.items}


def test_table_parser_can_be_replaced(fixture_pdf):
    def fake(pages):
        return [RawRow(page=1, name="Sodium (Na)", value="1", spec=None, unit="ppm", value_box=None,
                       row_box=Box(0, 0, 59.5, 84.2), confidence=0.9)]
    r = extract(fixture_pdf("COA_A_0007.pdf"), material_code="LIOH", table_parser=fake)
    assert [(i.normalized_name, i.bbox) for i in r.items] == [("Na", {"page": 1, "x": 0.0, "y": 0.0, "w": 0.0937, "h": 0.1079})]


def _render(pdf, path, dpi=200, skew=0.0):
    """PDF 첫 쪽을 이미지로 그린다 (스캔본 흉내). skew: 반시계 방향 회전 각도(도), 크기는 그대로."""
    with pymupdf.open(pdf) as doc:
        im = Image.open(io.BytesIO(doc[0].get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")
    if skew:
        im = im.rotate(skew, fillcolor="white", resample=Image.BICUBIC)
    im.save(path)
    return path


def _nums(text):
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def _center(bbox):
    return bbox["x"] + bbox["w"] / 2, bbox["y"] + bbox["h"] / 2


@pytest.mark.parametrize("name, suffix", [("COA_A_0007.pdf", ".png"), ("COA_B_0005.pdf", ".png"), ("COA_D_0007.pdf", ".jpg")])
def test_image_is_read_by_ocr(fixture_pdf, tmp_path, name, suffix):
    text = extract(fixture_pdf(name), material_code="LIOH")
    r = extract(_render(fixture_pdf(name), tmp_path / f"scan{suffix}"), material_code="LIOH")
    assert (r.doc_type, r.lot_no) == (text.doc_type, text.lot_no)
    assert [(i.normalized_name, _nums(i.raw_value)) for i in r.items] == \
        [(i.normalized_name, _nums(i.raw_value)) for i in text.items]
    # OCR 은 글자를 틀릴 수 있으므로 모두 '확인 필요'(서버 기준 0.8 미만)로 보낸다
    assert all(i.confidence <= OCR_CONFIDENCE_CAP < 0.8 for i in r.items)
    # 근거 위치는 같은 문서의 텍스트 PDF 결과와 같은 자리여야 한다 (쪽 크기 대비 비율)
    for o, t in zip(r.items, text.items):
        assert o.bbox["page"] == 1
        assert _center(o.bbox) == pytest.approx(_center(t.bbox), abs=0.02)


def test_skewed_image_bbox_points_at_original_position(fixture_pdf, tmp_path):
    text = extract(fixture_pdf("COA_A_0007.pdf"), material_code="LIOH")
    r = extract(_render(fixture_pdf("COA_A_0007.pdf"), tmp_path / "skew.png", skew=5), material_code="LIOH")
    assert len(r.items) == 15
    a = math.radians(5)
    for o, t in zip(r.items, text.items):
        # 텍스트 PDF 위치(pt)를 이미지와 같이 쪽 가운데 기준으로 반시계 5° 돌린 자리.
        # 되돌리지 않으면 최대 0.019 어긋나고, 되돌리면 0.003 이내다
        x, y = (c - 0.5 for c in _center(t.bbox))
        x, y = x * 595.3, y * 841.9
        expected = (0.5 + (x * math.cos(a) + y * math.sin(a)) / 595.3, 0.5 + (-x * math.sin(a) + y * math.cos(a)) / 841.9)
        assert _center(o.bbox) == pytest.approx(expected, abs=0.006)


def test_scanned_pdf_is_read_by_ocr(fixture_pdf, tmp_path):
    png = _render(fixture_pdf("COA_A_0007.pdf"), tmp_path / "a.png")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=png)
    doc.save(tmp_path / "scan.pdf")
    r = extract(tmp_path / "scan.pdf", material_code="LIOH")
    assert (r.lot_no, len(r.items)) == ("SL25-0008", 15)
    assert all(i.confidence <= OCR_CONFIDENCE_CAP for i in r.items)


def test_only_pages_without_text_are_ocred(fixture_pdf, tmp_path):
    """텍스트 쪽은 그대로 읽고(신뢰도 유지), 글자 없는 쪽만 OCR 한다."""
    doc = pymupdf.open(fixture_pdf("COA_A_0007.pdf"))
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=_render(fixture_pdf("COA_D_0007.pdf"), tmp_path / "d.png"))
    doc.save(tmp_path / "mixed.pdf")
    r = extract(tmp_path / "mixed.pdf", material_code="LIOH")
    first = [i for i in r.items if i.bbox["page"] == 1]
    second = [i for i in r.items if i.bbox["page"] == 2]
    assert (len(first), len(second)) == (15, 20)
    assert all(i.confidence >= 0.8 for i in first) and all(i.confidence <= OCR_CONFIDENCE_CAP for i in second)


def test_blank_scan_fails(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "blank.pdf")
    Image.new("RGB", (1654, 2339), "white").save(tmp_path / "blank.png")
    for path in (tmp_path / "blank.pdf", tmp_path / "blank.png"):
        with pytest.raises(ExtractionFailed) as e:
            extract(path, material_code="LI2CO3")
        assert str(e.value) == MSG_NO_TEXT


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".JPEG"])
def test_broken_image(tmp_path, suffix):
    path = tmp_path / f"scan{suffix}"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ExtractionFailed) as e:
        extract(path, material_code="LI2CO3")
    assert str(e.value) == MSG_BROKEN_IMAGE


def test_broken_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nbroken")
    with pytest.raises(ExtractionFailed) as e:
        extract(path, material_code="LI2CO3")
    assert str(e.value) == MSG_BROKEN


def test_spec_sheet_is_rejected(make_pdf):
    path = make_pdf(["Product Data Sheet", "Lithium Carbonate", "Na: <= 0.025 %"])
    with pytest.raises(ExtractionFailed) as e:
        extract(path, material_code="LI2CO3")
    assert str(e.value) == MSG_NOT_COA["spec_sheet"]


def test_coa_without_readable_table_returns_no_items(make_pdf):
    # 서버가 '문서에서 시험 항목을 찾을 수 없습니다' 로 실패 처리한다 (extraction_service)
    path = make_pdf(["Certificate of Analysis", [(50, "Lot Number"), (200, "A0266047")], "Signed by QA"])
    r = extract(path, material_code="LI2CO3")
    assert (r.doc_type, r.lot_no, r.items) == ("coa", "A0266047", [])


def test_encrypted_pdf(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 60), "Certificate of Analysis", fontsize=9)
    path = tmp_path / "locked.pdf"
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    with pytest.raises(ExtractionFailed) as e:
        extract(path, material_code="LI2CO3")
    assert str(e.value) == MSG_BROKEN


def test_same_standard_item_twice_is_kept(make_pdf):
    # Fisher 'Appearance (Color)', 'Appearance (Form)' 는 둘 다 외관. 합치지 않고 둘 다 넘긴다
    path = make_pdf([
        "Certificate of Analysis",
        [(50, "Lot Number"), (200, "A0386000")],
        [(40, "Result name"), (210, "Specifications"), (410, "Test Value")],
        [(40, "Appearance (Color)"), (210, "White"), (410, "White")],
        [(40, "Appearance (Form)"), (210, "Crystalline powder"), (410, "Crystalline powder")],
    ])
    r = extract(path, material_code="LI2CO3")
    assert [(i.raw_name, i.normalized_name) for i in r.items] == [
        ("Appearance (Color)", "외관"), ("Appearance (Form)", "외관"),
    ]


def test_coa_with_bare_lot_label_and_unknown_title_is_accepted(make_pdf):
    # 제목이 사전에 없어도(Analysis Report) 로트 + 결과 표가 있으면 CoA (잘못 막지 않기 우선)
    path = make_pdf([
        "Analysis Report",
        [(50, "Lot:"), (200, "AB12345")],
        [(40, "Item"), (210, "Specification"), (410, "Result")],
        [(40, "Sodium (Na)"), (210, "<= 50 ppm"), (410, "12 ppm")],
    ])
    r = extract(path, material_code="LI2CO3")
    assert (r.doc_type, r.lot_no, [i.normalized_name for i in r.items]) == ("coa", "AB12345", ["Na"])
