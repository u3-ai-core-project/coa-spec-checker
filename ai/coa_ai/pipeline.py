"""[담당: 고도영] 추출 파이프라인: 파일 → 줄 → 문서 유형 → 머리글 필드 → 표 → 항목명 정규화 → 결과.

표 구조화 함수(table_parser)는 바꿔 끼울 수 있다. 스캔본 단계에서 OCR/VLM 구조화기를 같은 자리에 넣는다.
실패하면 ExtractionFailed(화면에 보여줄 한국어 사유) 를 던진다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coa_ai.classify import ACCEPTED_DOC_TYPES, classify
from coa_ai.fields import extract_fields
from coa_ai.models import Box, Extraction, Item, Page, RawRow
from coa_ai.normalize import Normalizer
from coa_ai.pdf_text import PdfOpenError, read_pages
from coa_ai.table import parse_tables

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}

MSG_IMAGE = "이미지·스캔본 추출은 아직 지원하지 않습니다. 글자를 선택할 수 있는 PDF로 올려 주세요"
MSG_BROKEN = "PDF를 열 수 없습니다. 손상되었거나 암호가 걸린 파일인지 확인해 주세요"
MSG_NOT_COA = {
    "spec_sheet": "CoA가 아닌 문서입니다(규격서로 판단). 로트별 CoA 파일을 올려 주세요",
    "web_page": "CoA가 아닌 문서입니다(웹페이지 캡처로 판단, 로트 번호 없음). 로트별 CoA 파일을 올려 주세요",
    "other": "CoA로 볼 근거(제목·로트 번호·결과 표)를 찾지 못했습니다. CoA 파일이 맞는지 확인해 주세요",
}

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
    path = Path(path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        raise ExtractionFailed(MSG_IMAGE)
    try:
        pages = read_pages(path)
    except PdfOpenError as e:
        raise ExtractionFailed(MSG_BROKEN) from e
    if not any(p.lines for p in pages):
        raise ExtractionFailed(MSG_IMAGE)

    fields = extract_fields(pages)
    doc_type = classify(pages, has_lot=fields["lot_no"] is not None)
    if doc_type not in ACCEPTED_DOC_TYPES:
        raise ExtractionFailed(MSG_NOT_COA.get(doc_type, MSG_NOT_COA["other"]))

    normalizer = Normalizer(material_code, mappings)
    sizes = {p.number: (p.width, p.height) for p in pages}
    items = [_to_item(row, normalizer, sizes[row.page]) for row in table_parser(pages)]
    return Extraction(doc_type=doc_type, items=items, **fields)


def _to_item(row: RawRow, normalizer: Normalizer, size: tuple[float, float]) -> Item:
    mapping = normalizer.map(row.name)
    return Item(
        raw_name=row.name,
        normalized_name=mapping.name,
        mapping_source=mapping.source,
        raw_value=row.value,
        raw_spec=row.spec,
        unit=row.unit,
        confidence=round(min(row.confidence, mapping.cap), 2),
        bbox=_bbox(row.value_box or row.row_box, row.page, *size),
    )


def _bbox(box: Box, page: int, width: float, height: float) -> dict:
    """PDF 좌표 → 0~1 비율 (왼쪽 위 원점, page 는 1부터). 목업 default.json 과 같은 형식."""
    return {
        "page": page,
        "x": round(box.x0 / width, 4),
        "y": round(box.y0 / height, 4),
        "w": round(box.width / width, 4),
        "h": round(box.height / height, 4),
    }
