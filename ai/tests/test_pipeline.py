"""[담당: 고도영] extract() 전체 흐름과 결과 형식 (backend ExtractionInput 과 같은 형식)"""
import pytest

from coa_ai import ExtractionFailed, extract
from coa_ai.models import Box, RawRow
from coa_ai.pipeline import MSG_BROKEN, MSG_IMAGE, MSG_NOT_COA

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


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".JPEG"])
def test_images_are_not_supported_yet(tmp_path, suffix):
    path = tmp_path / f"scan{suffix}"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ExtractionFailed, match="이미지·스캔본"):
        extract(path, material_code="LI2CO3")


def test_scanned_pdf_without_text(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    path = tmp_path / "scan.pdf"
    doc.save(path)
    with pytest.raises(ExtractionFailed) as e:
        extract(path, material_code="LI2CO3")
    assert str(e.value) == MSG_IMAGE


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
