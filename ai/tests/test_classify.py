"""[담당: 고도영] 문서 유형 분류"""
import pytest

from coa_ai.classify import classify
from coa_ai.fields import extract_fields
from coa_ai.pdf_text import read_pages


def _classify(path):
    pages = read_pages(path)
    return classify(pages, has_lot=extract_fields(pages)["lot_no"] is not None)


@pytest.mark.parametrize("name", ["COA_A_0007.pdf", "COA_B_0005.pdf", "COA_D_0007.pdf"])
def test_synthetic_coa(fixture_pdf, name):
    assert _classify(fixture_pdf(name)) == "coa"


def test_coa_without_table_header(make_pdf):
    # Alfa 13418: 제목 + 로트 번호만으로도 CoA
    path = make_pdf(["Certificate of analysis", [(90, "Lot No.:"), (200, "U24E051")], [(225, "Na2O"), (330, "0.04 %")]])
    assert _classify(path) == "coa"


def test_spec_sheet(make_pdf):
    path = make_pdf(["Product Data Sheet", "Lithium Carbonate *Battery Grade", "Na: <= 0.025 %"])
    assert _classify(path) == "spec_sheet"


def test_web_page(make_pdf):
    path = make_pdf(["Home   Products   News   Contact Us   About Us   Blog",
                     "Battery-Grade Lithium Carbonate Powder", "Get the Latest Price"])
    assert _classify(path) == "web_page"


def test_other(make_pdf):
    path = make_pdf(["Quarterly Activities Report", "Lithium carbonate pilot samples"])
    assert _classify(path) == "other"
