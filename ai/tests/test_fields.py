"""[담당: 고도영] 머리글 필드"""
import pytest

from coa_ai.fields import extract_fields
from coa_ai.pdf_text import read_pages


@pytest.mark.parametrize("name, expected", [
    ("COA_A_0007.pdf", {"lot_no": "SL25-0008", "test_date": None, "expiry_date": "2027-12-27",
                        "supplier": "Selmora Lithium S.A.", "product_name": "LiOH Monohydrate (BG)",
                        "applied_standard": None, "origin": None}),
    ("COA_B_0005.pdf", {"lot_no": "LH26022103", "test_date": "2026-02-24", "issue_date": "2026-02-26",
                        "expiry_date": "2027-02-21", "supplier": "RUILAN LITHIUM (YICHUN) CO., LTD.",
                        "applied_standard": "GB/T 26008-2020 (D1)"}),
    ("COA_D_0007.pdf", {"lot_no": "KB26-063-02", "test_date": "2026-03-05",
                        "supplier": "Corvane Lithium Refining Pty Ltd", "applied_standard": "CVL-SPEC-LHM-BG Rev 4",
                        "product_name": "Lithium Hydroxide Monohydrate"}),
])
def test_synthetic_fields(fixture_pdf, name, expected):
    fields = extract_fields(read_pages(fixture_pdf(name)))
    assert {k: fields[k] for k in expected} == expected


def test_inline_colon_values_and_customer(make_pdf):
    path = make_pdf([
        "Acme Lithium Co., Ltd.",
        "LOT NO. : L0049ZH1",
        [(50, "Lot Size"), (200, "16,000 kg")],
        [(50, "Customer"), (200, "Sydco Co., Ltd.")],
        [(50, "Test Date :"), (200, "Aug 19, 2025")],
        "GRADE : Extra Pure",
    ])
    f = extract_fields(read_pages(path))
    assert (f["lot_no"], f["test_date"], f["supplier"], f["applied_standard"]) == \
        ("L0049ZH1", "2025-08-19", "Acme Lithium Co., Ltd.", "Extra Pure")


def test_lot_size_is_not_a_lot_number(make_pdf):
    path = make_pdf([[(50, "Lot Size"), (200, "16,000 kg")]])
    assert extract_fields(read_pages(path))["lot_no"] is None


def test_manufacture_date_is_not_used_as_test_date(make_pdf):
    path = make_pdf([[(50, "Date of Manufacture"), (200, "27-Dec-2025")], [(50, "Lot Number"), (200, "A0266047")]])
    f = extract_fields(read_pages(path))
    assert (f["lot_no"], f["test_date"]) == ("A0266047", None)
