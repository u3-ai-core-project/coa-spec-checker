"""[담당: 장수민] 문서 정합성 검사 (명세 v1.4 2.1 document_issues, 멘토님 범위 정의서 데모 12).

항목 판정과 별개로 문서 단위 문제를 찾는다. 1개 이상이면 부적합이 없어도 보류 권고다 (lot_recommend).

  LOT_MISMATCH   입고 로트번호(업로드 때 입력) ≠ CoA 로트번호
  DATE_CONFLICT  CoA 발행일이 시험일보다 앞섬, 또는 유효기한이 시험일보다 앞섬
  SPEC_VERSION_UNKNOWN  CoA 적용 규격과 사내 규격 세트가 같은 규격의 다른 버전 (데모 18, E04)
                        예) CoA "YS/T 582-2023", 사내 세트 "YS/T 582-2013" → 어느 버전으로 판정할지 확인 필요
                        (새 코드를 만들면 결과 JSON 스키마 변경이라, 기존 코드에 메시지로 구분한다)

한쪽 값이 없으면 검사하지 않는다 (모르는 것을 오류로 만들지 않는다).
로트번호는 대소문자·공백·구분 기호(- _ / .)만 다른 경우 같은 로트로 본다 (예: "L-080" = "l080").
"""
import re
from datetime import date

from app.core.enums import DocumentIssueCode as D
from app.schemas.extraction import DocumentIssue, ExtractionInput

_LOT_SEPARATORS = re.compile(r"[\s\-_/.]+")


def normalize_lot(lot: str | None) -> str:
    return _LOT_SEPARATORS.sub("", lot or "").upper()


def check_lot(received_lot_no: str | None, coa_lot_no: str | None) -> DocumentIssue | None:
    received, coa = normalize_lot(received_lot_no), normalize_lot(coa_lot_no)
    if not received or not coa or received == coa:
        return None
    return DocumentIssue(code=D.LOT_MISMATCH,
                         message=f"입고 로트 {received_lot_no.strip()} ≠ CoA 로트 {coa_lot_no.strip()}")


def check_dates(extraction: ExtractionInput) -> DocumentIssue | None:
    test, issue, expiry = extraction.test_date, extraction.issue_date, extraction.expiry_date
    problems: list[str] = []
    if test and issue and issue < test:
        problems.append(f"발행일 {_d(issue)}이 시험일 {_d(test)}보다 앞섬")
    if test and expiry and expiry < test:
        problems.append(f"유효기한 {_d(expiry)}이 시험일 {_d(test)}보다 앞섬")
    if not problems:
        return None
    return DocumentIssue(code=D.DATE_CONFLICT, message=", ".join(problems))


# 규격 번호 + 연도. 예) "YS/T 582-2023", "GB/T 11075-2013", "YS/T582—2013 D1"
_STANDARD = re.compile(r"([A-Z]{1,4}(?:\s*/\s*[A-Z]{1,4})?)\s*(\d+(?:\.\d+)?)\s*[-–—]\s*((?:19|20)\d{2})")


def parse_standard(text: str | None) -> tuple[str, str] | None:
    """규격 문자열 → (규격 번호, 연도). 예) "YS/T 582-2023 D1" → ("YS/T582", "2023"). 못 읽으면 None."""
    m = _STANDARD.search((text or "").upper())
    if not m:
        return None
    return re.sub(r"\s+", "", m.group(1)) + m.group(2), m.group(3)


def check_spec_version(applied_standard: str | None, spec_version: str | None) -> DocumentIssue | None:
    coa, ours = parse_standard(applied_standard), parse_standard(spec_version)
    if not coa or not ours or coa[0] != ours[0] or coa[1] == ours[1]:
        return None
    return DocumentIssue(code=D.SPEC_VERSION_UNKNOWN,
                         message=f"CoA 적용 규격 {applied_standard.strip()} ≠ 사내 규격 세트 버전 {spec_version.strip()} "
                                 f"(같은 규격의 다른 버전)")


def check_document(extraction: ExtractionInput, *, received_lot_no: str | None = None,
                   spec_version: str | None = None) -> list[DocumentIssue]:
    """문서 정합성 오류 목록 (없으면 빈 목록).

    received_lot_no : 업로드 때 입력한 입고 로트번호
    spec_version    : 이 문서를 판정한 사내 규격 세트의 버전 (spec_sets.version)
    """
    checks = (
        check_lot(received_lot_no, extraction.lot_no),
        check_dates(extraction),
        check_spec_version(extraction.applied_standard, spec_version),
    )
    return [i for i in checks if i]


def _d(value: date) -> str:
    return value.isoformat()
