"""[담당: 장수민] 문서 정합성 검사 (명세 v1.4 2.1 document_issues, 멘토님 범위 정의서 데모 12).

항목 판정과 별개로 문서 단위 문제를 찾는다. 1개 이상이면 부적합이 없어도 보류 권고다 (lot_recommend).

  LOT_MISMATCH   입고 로트번호(업로드 때 입력) ≠ CoA 로트번호
  DATE_CONFLICT  CoA 발행일이 시험일·제조일보다 앞섬, 유효기한이 시험일보다 앞섬,
                 또는 입고일(일괄 접수의 입고 CSV)이 유효기한·재시험일을 지남
  SPEC_VERSION_MISMATCH CoA 적용 규격과 사내 규격 세트가 같은 규격의 다른 연도판 (데모 18, E04)
                        예) CoA "YS/T 582-2023", 사내 세트 "YS/T 582-2013" → 어느 버전으로 판정할지 확인 필요
                        (이전 이름 SPEC_VERSION_UNKNOWN 은 "모름"이라는 뜻이라 실제 상황과 달라 바꿨다. 10.25 회의 결정)

  MULTI_LOT      한 문서에서 로트번호가 2개 이상 확인됨 (운영 정책 8.1). 문서 하나에 로트 하나를 전제할 수 없어 담당자 확인으로 넘긴다.
                 첫 로트만 채택하면 나머지 로트가 대조·판정에서 빠져 조용히 통과하므로 lot_no 는 비우고 lot_nos 에 전체를 담는다

  PRODUCT_MISMATCH CoA 제품명이 접수한 원자재가 아닌 다른 원자재를 가리킴 (UC07)
                   예) 탄산리튬으로 접수했는데 CoA 제품명이 "Lithium Hydroxide Monohydrate"
                   표기가 협력사마다 달라 문자열 비교는 하지 않고, 원자재 키워드가 서로 충돌할 때만 경고한다
                   (일괄 접수에서 입고 원자재가 다른 경우의 PRODUCT_MISMATCH 는 batch_service.link_by_lot 이 찾는다)

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


def distinct_lots(extraction: ExtractionInput) -> list[str]:
    """문서에서 읽은 로트번호 (lot_no + lot_nos). 정규화했을 때 같은 로트는 한 번만, 처음 쓴 표기로 남긴다."""
    seen: dict[str, str] = {}
    for lot in [extraction.lot_no, *extraction.lot_nos]:
        key = normalize_lot(lot)
        if key and key not in seen:
            seen[key] = lot.strip()
    return list(seen.values())


def check_multi_lot(lots: list[str], received_lot_no: str | None) -> list[DocumentIssue]:
    """복수 로트 문서 표시. 입고 로트를 입력했는데 CoA 의 로트들 중에 없으면 LOT_MISMATCH 도 낸다."""
    shown = ", ".join(lots[:5]) + (f" 외 {len(lots) - 5}개" if len(lots) > 5 else "")
    issues = [DocumentIssue(code=D.MULTI_LOT,
                            message=f"한 문서에서 로트 {len(lots)}개가 확인됨 ({shown}). 로트별로 입고 로트와 대조하고 판정해야 함")]
    received = normalize_lot(received_lot_no)
    if received and received not in {normalize_lot(lot) for lot in lots}:
        issues.append(DocumentIssue(code=D.LOT_MISMATCH,
                                    message=f"입고 로트 {received_lot_no.strip()} 가 CoA 로트 {shown} 에 없음"))
    return issues


def check_lot(received_lot_no: str | None, coa_lot_no: str | None) -> DocumentIssue | None:
    received, coa = normalize_lot(received_lot_no), normalize_lot(coa_lot_no)
    if not received or not coa or received == coa:
        return None
    return DocumentIssue(code=D.LOT_MISMATCH,
                         message=f"입고 로트 {received_lot_no.strip()} ≠ CoA 로트 {coa_lot_no.strip()}")


def check_dates(extraction: ExtractionInput, received_date: date | None = None) -> DocumentIssue | None:
    test, issue, expiry, retest = extraction.test_date, extraction.issue_date, extraction.expiry_date, extraction.retest_date
    problems: list[str] = []
    if extraction.manufacture_date and issue and issue < extraction.manufacture_date:
        problems.append(f"발행일 {_d(issue)}이 제조일 {_d(extraction.manufacture_date)}보다 앞섬")
    if test and issue and issue < test:
        problems.append(f"발행일 {_d(issue)}이 시험일 {_d(test)}보다 앞섬")
    if test and expiry and expiry < test:
        problems.append(f"유효기한 {_d(expiry)}이 시험일 {_d(test)}보다 앞섬")
    # 입고 시점에 이미 유효기한·재시험일이 지난 원료 (생성기 v2 DATE_CONFLICT 사례)
    if received_date and expiry and received_date > expiry:
        problems.append(f"입고일 {_d(received_date)}이 유효기한 {_d(expiry)}을 지남")
    if received_date and retest and received_date > retest:
        problems.append(f"입고일 {_d(received_date)}이 재시험일 {_d(retest)}을 지남")
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
    return DocumentIssue(code=D.SPEC_VERSION_MISMATCH,
                         message=f"CoA 적용 규격 {applied_standard.strip()} ≠ 사내 규격 세트 버전 {spec_version.strip()} "
                                 f"(같은 규격의 다른 버전)")


# 원자재별 제품명 키워드 (소문자). 제품명이 다른 원자재의 키워드만 담고 접수 원자재의 키워드는 없으면 불일치
_PRODUCT_KEYWORDS = {
    "LI2CO3": ("carbonate", "li2co3", "탄산", "碳酸"),
    "LIOH": ("hydroxide", "lioh", "수산화", "氢氧化", "氫氧化"),
}


def check_product(product_name: str | None, material_code: str | None) -> DocumentIssue | None:
    name = (product_name or "").lower()
    own = _PRODUCT_KEYWORDS.get((material_code or "").upper())
    if not name.strip() or own is None or any(k in name for k in own):
        return None
    others = [code for code, keys in _PRODUCT_KEYWORDS.items()
              if keys is not own and any(k in name for k in keys)]
    if not others:
        return None
    return DocumentIssue(code=D.PRODUCT_MISMATCH,
                         message=f"CoA 제품명 {product_name.strip()} 이(가) 접수 원자재 {material_code.upper()} 가 아니라 "
                                 f"{others[0]} 로 보임")


def check_document(extraction: ExtractionInput, *, received_lot_no: str | None = None,
                   spec_version: str | None = None, received_date: date | None = None,
                   material_code: str | None = None) -> list[DocumentIssue]:
    """문서 정합성 오류 목록 (없으면 빈 목록).

    received_lot_no : 업로드 때 입력한 입고 로트번호
    spec_version    : 이 문서를 판정한 사내 규격 세트의 버전 (spec_sets.version)
    received_date   : 입고일 (일괄 접수에서 입고 행과 연결된 경우만)
    material_code   : 접수한 원자재 (CoA 제품명 비교용)
    """
    lots = distinct_lots(extraction)
    lot_issues = check_multi_lot(lots, received_lot_no) if len(lots) >= 2 else [check_lot(received_lot_no, extraction.lot_no)]
    checks = (
        *lot_issues,
        check_dates(extraction, received_date),
        check_spec_version(extraction.applied_standard, spec_version),
        check_product(extraction.product_name, material_code),
    )
    return [i for i in checks if i]


def _d(value: date) -> str:
    return value.isoformat()
