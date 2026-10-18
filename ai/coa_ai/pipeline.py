"""[담당: 고도영] 추출 파이프라인: 파일 → 줄 → 문서 유형 → 머리글 필드 → 표 → 항목명 정규화 → 결과.

텍스트 PDF 는 글자 층을 읽고, 이미지 파일과 글자 없는 PDF 쪽(스캔본)은 OCR 로 읽는다 (coa_ai.ocr).
표 구조화 함수(table_parser)는 바꿔 끼울 수 있다.
실패하면 ExtractionFailed(화면에 보여줄 한국어 사유) 를 던진다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coa_ai.classify import ACCEPTED_DOC_TYPES, classify
from coa_ai.fields import extract_fields
from coa_ai.models import Box, Extraction, Item, Page, RawRow
from coa_ai.normalize import Normalizer
from coa_ai.ocr import ImageOpenError, read_image, read_pdf_page
from coa_ai.pdf_text import PdfOpenError, read_pages
from coa_ai.table import parse_tables

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}

MSG_BROKEN = "PDF를 열 수 없습니다. 손상되었거나 암호가 걸린 파일인지 확인해 주세요"
MSG_BROKEN_IMAGE = "이미지 파일을 열 수 없습니다. 손상된 파일인지 확인해 주세요"
MSG_NO_TEXT = "문서에서 글자를 찾지 못했습니다. 글자가 선명하게 보이는 스캔본인지 확인해 주세요"
MSG_NOT_COA = {
    "spec_sheet": "CoA가 아닌 문서입니다(규격서로 판단). 로트별 CoA 파일을 올려 주세요",
    "web_page": "CoA가 아닌 문서입니다(웹페이지 캡처로 판단, 로트 번호 없음). 로트별 CoA 파일을 올려 주세요",
    "other": "CoA로 볼 근거(제목·로트 번호·결과 표)를 찾지 못했습니다. CoA 파일이 맞는지 확인해 주세요",
}

# OCR 은 글자를 틀릴 수 있고(모델 테스트 값 일치율 약 90%), 틀린 글자도 OCR 점수가 높아 가려낼 수 없다.
# 그래서 OCR 로 읽은 항목은 모두 서버 기준(0.8) 아래로 두어 담당자 확인을 거치게 한다.
OCR_CONFIDENCE_CAP = 0.75

TableParser = Callable[[list[Page]], list[RawRow]]


class ExtractionFailed(Exception):
    """추출 실패. 메시지는 업로드 화면에 그대로 표시된다."""


def extract(
    path: str | Path,
    *,
    material_code: str,
    mappings: dict[str, str] | None = None,
    table_parser: TableParser = parse_tables,
) -> Extraction:
    """CoA 파일 1건을 읽는다.

    material_code : 원자재 구분(LI2CO3, LIOH). 항목명 사전을 원자재별로 고른다.
    mappings      : DB item_mappings 의 {원문 항목명: 표준 항목명}. 사전보다 먼저 본다.
    """
    pages = _read(Path(path))
    if not any(p.lines for p in pages):
        raise ExtractionFailed(MSG_NO_TEXT)

    fields = extract_fields(pages)
    doc_type = classify(pages, has_lot=fields["lot_no"] is not None)
    if doc_type not in ACCEPTED_DOC_TYPES:
        raise ExtractionFailed(MSG_NOT_COA.get(doc_type, MSG_NOT_COA["other"]))

    normalizer = Normalizer(material_code, mappings)
    by_number = {p.number: p for p in pages}
    items = [_to_item(row, normalizer, by_number[row.page]) for row in table_parser(pages)]
    return Extraction(doc_type=doc_type, items=items, **fields)


def _read(path: Path) -> list[Page]:
    """파일 → 쪽 목록. 이미지는 OCR, PDF 는 글자 층을 읽고 글자 없는 쪽만 OCR 한다."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        try:
            return [read_image(path)]
        except ImageOpenError as e:
            raise ExtractionFailed(MSG_BROKEN_IMAGE) from e
    try:
        pages = read_pages(path)
    except PdfOpenError as e:
        raise ExtractionFailed(MSG_BROKEN) from e
    return [p if p.lines else read_pdf_page(path, p.number) for p in pages]


def _to_item(row: RawRow, normalizer: Normalizer, page: Page) -> Item:
    mapping = normalizer.map(row.name)
    confidence = min(row.confidence, mapping.cap, OCR_CONFIDENCE_CAP if page.ocr else 1.0)
    return Item(
        raw_name=row.name,
        normalized_name=mapping.name,
        mapping_source=mapping.source,
        raw_value=row.value,
        raw_spec=row.spec,
        unit=row.unit,
        confidence=round(confidence, 2),
        bbox=_bbox(page.to_image_box(row.value_box or row.row_box), page),
    )


def _bbox(box: Box, page: Page) -> dict:
    """쪽 좌표 → 0~1 비율 (왼쪽 위 원점, page 는 1부터). 목업 default.json 과 같은 형식."""
    return {
        "page": page.number,
        "x": round(box.x0 / page.width, 4),
        "y": round(box.y0 / page.height, 4),
        "w": round(box.width / page.width, 4),
        "h": round(box.height / page.height, 4),
    }
