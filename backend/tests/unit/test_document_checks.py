"""[담당: 장수민] 문서 정합성 검사 테스트 (명세 v1.4 2.1, 멘토님 데모 12·18)."""
from datetime import date

import pytest

from app.core.enums import DocumentIssueCode as D
from app.schemas.extraction import ExtractionInput
from app.services.judgement.document_checks import check_document, parse_standard


def coa(**kw) -> ExtractionInput:
    return ExtractionInput(items=[], **kw)


def codes(issues) -> list[str]:
    return [i.code for i in issues]


# ---- 로트 ------------------------------------------------------------------
def test_lot_mismatch():
    issues = check_document(coa(lot_no="L-2409-01"), received_lot_no="L-2409-02")
    assert codes(issues) == [D.LOT_MISMATCH]
    assert "L-2409-02" in issues[0].message and "L-2409-01" in issues[0].message


@pytest.mark.parametrize("received, coa_lot", [
    ("L-080", "L080"), ("l 080", "L-080"), ("A0396981", "a0396981"), ("24/09.01", "240901"),
])
def test_lot_format_only_differences_are_same_lot(received, coa_lot):
    assert check_document(coa(lot_no=coa_lot), received_lot_no=received) == []


@pytest.mark.parametrize("received, coa_lot", [(None, "L-1"), ("L-1", None), ("  ", "L-1")])
def test_lot_not_checked_when_either_side_missing(received, coa_lot):
    assert check_document(coa(lot_no=coa_lot), received_lot_no=received) == []


# ---- 날짜 ------------------------------------------------------------------
def test_issue_date_before_test_date():
    issues = check_document(coa(test_date=date(2026, 9, 20), issue_date=date(2026, 9, 18)))
    assert codes(issues) == [D.DATE_CONFLICT]
    assert "발행일" in issues[0].message


def test_expiry_before_test_date():
    issues = check_document(coa(test_date=date(2026, 9, 20), expiry_date=date(2026, 9, 1)))
    assert codes(issues) == [D.DATE_CONFLICT] and "유효기한" in issues[0].message


def test_received_after_expiry_or_retest():
    """입고 시점에 유효기한·재시험일이 지난 원료 (생성기 v2 DATE_CONFLICT)."""
    doc = coa(test_date=date(2026, 1, 10), expiry_date=date(2026, 9, 30), retest_date=date(2026, 7, 1))
    issues = check_document(doc, received_date=date(2026, 10, 5))
    assert codes(issues) == [D.DATE_CONFLICT]
    assert "유효기한 2026-09-30" in issues[0].message and "재시험일 2026-07-01" in issues[0].message


def test_received_before_expiry_is_fine():
    doc = coa(expiry_date=date(2027, 9, 30), retest_date=date(2027, 3, 1))
    assert check_document(doc, received_date=date(2026, 10, 5)) == []
    assert check_document(doc) == []          # 입고일을 모르면 검사하지 않음


def test_dates_in_order_are_fine():
    ok = coa(test_date=date(2026, 9, 20), issue_date=date(2026, 9, 20), expiry_date=date(2028, 9, 20))
    assert check_document(ok) == []


# ---- 규격 버전 (데모 18) ------------------------------------------------------
def test_same_standard_different_version():
    issues = check_document(coa(applied_standard="YS/T 582-2023 D1"), spec_version="YS/T 582-2013")
    assert codes(issues) == [D.SPEC_VERSION_MISMATCH]
    assert "YS/T 582-2023 D1" in issues[0].message and "YS/T 582-2013" in issues[0].message


@pytest.mark.parametrize("applied, version", [
    ("YS/T 582-2023 D1", "YS/T 582-2023"),        # 같은 버전
    ("GB/T 11075-2013", "YS/T 582-2023"),         # 다른 규격 (비교 대상 아님)
    ("Battery grade", "YS/T 582-2023"),           # 규격 번호 없음
    ("YS/T 582-2013", "SYD-QS-LC-BG v1"),         # 사내 세트 버전을 읽을 수 없음
    (None, "YS/T 582-2023"),
])
def test_spec_version_no_issue(applied, version):
    assert check_document(coa(applied_standard=applied), spec_version=version) == []


@pytest.mark.parametrize("text, parsed", [
    ("YS/T 582-2023", ("YS/T582", "2023")),
    ("ys/t582—2013 D1", ("YS/T582", "2013")),
    ("GB/T 11075-2013", ("GB/T11075", "2013")),
    ("Q/SYD 01-2020", ("Q/SYD01", "2020")),
    ("Battery grade", None),
])
def test_parse_standard(text, parsed):
    assert parse_standard(text) == parsed


def test_several_issues_together():
    doc = coa(lot_no="L-1", test_date=date(2026, 9, 20), issue_date=date(2026, 9, 1), applied_standard="YS/T 582-2023")
    issues = check_document(doc, received_lot_no="L-2", spec_version="YS/T 582-2013")
    assert codes(issues) == [D.LOT_MISMATCH, D.DATE_CONFLICT, D.SPEC_VERSION_MISMATCH]


# ---- 제조일, AI 제안 칸 (10.25 회의 결정) -------------------------------------
def test_issue_date_before_manufacture_date():
    issues = check_document(coa(manufacture_date=date(2026, 9, 10), issue_date=date(2026, 9, 5)))
    assert codes(issues) == [D.DATE_CONFLICT]
    assert "제조일" in issues[0].message


def test_manufacture_date_before_issue_date_is_fine():
    assert check_document(coa(manufacture_date=date(2026, 9, 1), issue_date=date(2026, 9, 5))) == []
    assert check_document(coa(manufacture_date=date(2026, 9, 1))) == []   # 발행일을 모르면 검사하지 않음


def test_ai_proposal_fields_are_kept_in_result():
    from app.services.judgement.engine import judge_document
    from app.services.judgement.spec_rule import SpecRule
    inp = ExtractionInput.model_validate({"manufacture_date": "2026-09-01", "items": [
        {"normalized_name": "Na", "raw_value": "30", "unit": "ppm", "confidence": 0.9,
         "value_kind": "number", "value_reason": "숫자 + 단위", "check_reasons": ["x"]}]})
    result = judge_document(inp, document_id="d", specs=[SpecRule("Na", unit="ppm", usl=50)]).to_json()
    item = result["items"][0]
    assert (item["value_kind"], item["value_reason"], item["check_reasons"]) == ("number", "숫자 + 단위", ["x"])
    assert result["manufacture_date"] == "2026-09-01"


# ---- 제품명 (UC07): 접수 원자재와 다른 원자재를 가리킬 때만 -------------------------
@pytest.mark.parametrize("name, material", [
    ("Lithium Hydroxide Monohydrate Battery Grade", "LI2CO3"),
    ("수산화리튬 일수화물", "LI2CO3"),
    ("氢氧化锂", "LI2CO3"),
    ("Lithium Carbonate Battery Grade", "LIOH"),
    ("碳酸锂", "LIOH"),
])
def test_product_name_points_to_other_material(name, material):
    issues = check_document(coa(product_name=name), material_code=material)
    assert codes(issues) == [D.PRODUCT_MISMATCH]
    assert name in issues[0].message


@pytest.mark.parametrize("name, material", [
    ("Lithium Carbonate Battery Grade", "LI2CO3"),
    ("LI2CO3 99.5%", "li2co3"),
    ("Lithium Hydroxide Monohydrate", "LIOH"),
    ("Battery Grade Lithium", "LI2CO3"),      # 어느 원자재인지 알 수 없는 표기 → 경고하지 않는다
    ("Lithium Carbonate / Lithium Hydroxide", "LI2CO3"),  # 접수 원자재 키워드가 있으면 경고하지 않는다
    ("", "LI2CO3"),
    (None, "LI2CO3"),
    ("Lithium Hydroxide", "NI"),             # 키워드를 모르는 원자재는 검사하지 않는다
    ("Lithium Hydroxide", None),
])
def test_product_name_no_issue(name, material):
    assert check_document(coa(product_name=name), material_code=material) == []
