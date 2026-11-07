"""[담당: 고도영] 추출 파이프라인: 파일 → 줄 → 문서 유형 → 머리글 필드 → 표 → 항목명 정규화·결과 의미 → 자체 검증 → 결과.

텍스트 PDF 는 글자 층을 읽고, 이미지 파일과 글자 없는 PDF 쪽(스캔본)은 OCR 로 읽는다 (coa_ai.ocr).
표 구조화 함수(table_parser)는 바꿔 끼울 수 있다.
LLM(llm)을 넘기면 규칙이 못 읽은 항목명·결과 칸만 LLM 에 묻는다. 없거나 실패해도 결과는 나온다.
실패하면 ExtractionFailed(화면에 보여줄 한국어 사유) 를 던진다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coa_ai.classify import ACCEPTED_DOC_TYPES, classify
from coa_ai.fields import extract_fields
from coa_ai.llm import LLMClient
from coa_ai.meaning import classify as classify_value
from coa_ai.models import Box, Extraction, Item, Page, RawRow
from coa_ai.normalize import AI_CAP, Mapping, Normalizer
from coa_ai.ocr import ImageOpenError, read_image, read_pdf_page
from coa_ai.pdf_text import PdfOpenError, image_body_pages, read_pages
from coa_ai.selfcheck import check_items
from coa_ai.table import CONF_FIXED, CONF_LIST, parse_tables

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}

MSG_BROKEN = "PDF를 열 수 없습니다. 손상되었거나 암호가 걸린 파일인지 확인해 주세요"
MSG_BROKEN_IMAGE = "이미지 파일을 열 수 없습니다. 손상된 파일인지 확인해 주세요"
MSG_NO_TEXT = "문서에서 글자를 찾지 못했습니다. 글자가 선명하게 보이는 스캔본인지 확인해 주세요"
MSG_NOT_COA = {
    "spec_sheet": "CoA가 아닌 문서입니다(규격서로 판단). 로트별 CoA 파일을 올려 주세요",
    "web_page": "CoA가 아닌 문서입니다(웹페이지 캡처로 판단, 로트 번호 없음). 로트별 CoA 파일을 올려 주세요",
    "other": "CoA로 볼 근거(제목·로트 번호·결과 표)를 찾지 못했습니다. CoA 파일이 맞는지 확인해 주세요",
}

# OCR 은 글자를 틀릴 수 있고(모델 테스트 152장 수치 일치율 99%, 실제 스캔본은 더 거칠 수 있다), 틀린 글자도 OCR 점수가 높아 가려낼 수 없다.
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
    llm: LLMClient | None = None,
) -> Extraction:
    """CoA 파일 1건을 읽는다.

    material_code : 원자재 구분(LI2CO3, LIOH). 항목명 사전을 원자재별로 고른다.
    mappings      : DB item_mappings 의 {원문 항목명: 표준 항목명}. 사전보다 먼저 본다.
    llm           : LLM 서버 클라이언트. 문서 1건마다 호출 상한을 새로 센다 (LLMClient.for_document).
    """
    pages = _read(Path(path))
    if not any(p.lines for p in pages):
        raise ExtractionFailed(MSG_NO_TEXT)

    fields = extract_fields(pages)
    doc_type = classify(pages, has_lot=fields["lot_no"] is not None)
    if doc_type not in ACCEPTED_DOC_TYPES:
        raise ExtractionFailed(MSG_NOT_COA.get(doc_type, MSG_NOT_COA["other"]))

    doc_llm = llm.for_document() if llm is not None else None
    normalizer = Normalizer(material_code, mappings, llm=doc_llm)
    by_number = {p.number: p for p in pages}
    rows = table_parser(pages)
    mappings = _drop_duplicate_suggestions(rows, [normalizer.map(row.name) for row in rows])
    items = [_to_item(row, m, by_number[row.page], doc_llm) for row, m in zip(rows, mappings)]
    check_items(items)  # 틀렸을 가능성이 높은 항목은 확인 필요(신뢰도 0.75 이하) + 이유
    return Extraction(doc_type=doc_type, items=items, **fields)


def _read(path: Path) -> list[Page]:
    """파일 → 쪽 목록. 이미지는 OCR, PDF 는 글자 층을 읽고 글자 없는 쪽과 본문이 스캔 이미지인 쪽을 OCR 한다."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        try:
            return [read_image(path)]
        except ImageOpenError as e:
            raise ExtractionFailed(MSG_BROKEN_IMAGE) from e
    try:
        pages = read_pages(path)
    except PdfOpenError as e:
        raise ExtractionFailed(MSG_BROKEN) from e
    scanned = image_body_pages(path)
    return [p if p.lines and p.number not in scanned else _ocr_page(path, p) for p in pages]


def _ocr_page(path: Path, text_page: Page) -> Page:
    """OCR 로 다시 읽는다. 글자 층이 있던 쪽은 OCR 이 빈손이면 글자 층 결과를 그대로 쓴다."""
    page = read_pdf_page(path, text_page.number)
    return page if page.lines or not text_page.lines else text_page


def _drop_duplicate_suggestions(rows: list[RawRow], mappings: list[Mapping]) -> list[Mapping]:
    """같은 문서에서 사전으로 확정된 표준 항목명을 LLM 이 또 제안하면 받지 않는다.

    CoA 에는 같은 시험 항목이 보통 한 번 나온다. 실물에서 'Traceable to' 같은 시험 항목 아닌 행을 LLM 이
    이미 있는 '순도'로 제안해, '참고'로 지나갈 행이 확인 필요(로트 보류)가 되는 일이 있었다.
    """
    confirmed = {m.name for m in mappings if m.source == "dictionary"}
    return [Mapping(row.name, "ai", AI_CAP) if m.by_llm and m.name in confirmed else m
            for row, m in zip(rows, mappings)]


def _to_item(row: RawRow, mapping: Mapping, page: Page, llm: LLMClient | None = None) -> Item:
    meaning = classify_value(row.value, row.spec, llm, raw_name=row.name)
    base = row.confidence
    if base == CONF_LIST and mapping.source == "dictionary":
        # 머리글 없는 목록·격자도 이름을 사전으로 확정했으면 칸 보정 행과 같게 본다 (실물 라벨 대조 42/42 정확).
        # OCR 로 읽은 쪽은 아래 OCR 상한(0.75)이 그대로 걸린다
        base = CONF_FIXED
    confidence = min(base, mapping.cap, OCR_CONFIDENCE_CAP if page.ocr else 1.0)
    return Item(
        raw_name=row.name,
        normalized_name=mapping.name,
        mapping_source=mapping.source,
        raw_value=row.value,
        raw_spec=row.spec,
        unit=row.unit,
        confidence=round(confidence, 2),
        bbox=_bbox(page.to_image_box(row.value_box or row.row_box), page),
        value_kind=meaning.kind,
        value_reason=meaning.reason,
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
