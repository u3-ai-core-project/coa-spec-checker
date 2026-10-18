"""[담당: 고도영] 추출 파이프라인이 주고받는 데이터 구조.

좌표는 PDF 포인트 단위(왼쪽 위 원점)로 다루고, 결과로 내보낼 때만 0~1 비율로 바꾼다.
결과 dict 형식은 backend/app/schemas/extraction.py 의 ExtractionInput 과 같다 (추가 필드는 서버가 무시).
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def union(self, other: Box) -> Box:
        return Box(min(self.x0, other.x0), min(self.y0, other.y0), max(self.x1, other.x1), max(self.y1, other.y1))

    def x_overlap(self, x0: float, x1: float) -> float:
        return max(0.0, min(self.x1, x1) - max(self.x0, x0))

    @staticmethod
    def around(boxes: Iterable[Box]) -> Box:
        boxes = list(boxes)
        out = boxes[0]
        for b in boxes[1:]:
            out = out.union(b)
        return out


@dataclass(frozen=True)
class Word:
    """공백이나 넓은 간격 없이 붙어 있는 글자 묶음."""
    text: str
    box: Box
    size: float  # 글자 크기(pt)


@dataclass
class Line:
    """기준선이 같은 단어들 (첨자는 이미 끼워 넣은 상태). x 순서로 정렬돼 있다."""
    words: list[Word]
    page: int  # 1부터
    baseline: float
    size: float  # 줄의 대표 글자 크기

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def box(self) -> Box:
        return Box.around(w.box for w in self.words)


@dataclass(frozen=True)
class Phrase:
    """한 줄 안에서 좁은 간격으로 이어진 단어들. 표의 칸이나 '라벨 값' 의 한쪽이 된다."""
    text: str
    box: Box
    line: int  # Page.lines 안의 줄 번호


@dataclass
class Page:
    number: int  # 1부터
    width: float
    height: float
    lines: list[Line]
    skew: float = 0.0  # OCR 로 바로 세운 각도(라디안, 쪽 가운데 기준). 텍스트 PDF 는 0
    ocr: bool = False  # 스캔본·이미지를 OCR 로 읽은 쪽

    def to_image_box(self, box: Box) -> Box:
        """바로 세운 좌표의 상자 → 원본 이미지 좌표의 상자 (기울기를 되돌린 네 꼭짓점을 감싸는 상자)."""
        if not self.skew:
            return box
        cx, cy = self.width / 2, self.height / 2
        cos, sin = math.cos(self.skew), math.sin(self.skew)
        pts = [(cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos)
               for x, y in ((box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1))]
        return Box(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


@dataclass
class RawRow:
    """표에서 읽은 시험 항목 1행. 값은 해석하지 않은 원문 그대로다."""
    page: int
    name: str
    value: str | None
    spec: str | None
    unit: str | None
    value_box: Box | None
    row_box: Box
    confidence: float


@dataclass
class Item:
    """서버로 넘기는 항목 1개 (ExtractedItem 형식)."""
    raw_name: str
    normalized_name: str
    mapping_source: str  # dictionary | ai
    raw_value: str | None
    raw_spec: str | None
    unit: str | None
    confidence: float
    bbox: dict | None  # {"page": 1부터, "x", "y", "w", "h": 0~1 비율}
    # 결과 의미 (coa_ai.meaning, 팀 제안 칸). 서버 ExtractedItem 은 아직 이 칸을 무시한다 (extra="ignore")
    value_kind: str | None = None    # number | bound | nd | spec_copy | pass_text | description
    value_reason: str | None = None  # 근거 한 줄. LLM 이 정했으면 "AI 판단: " 으로 시작


@dataclass
class Extraction:
    """문서 1건의 추출 결과 (ExtractionInput 형식 + 추가 필드)."""
    doc_type: str
    supplier: str | None = None
    lot_no: str | None = None
    test_date: str | None = None  # YYYY-MM-DD
    origin: str | None = None
    applied_standard: str | None = None
    product_name: str | None = None  # API v1.4 대비 (현재 서버는 무시)
    issue_date: str | None = None    # API v1.4 대비
    expiry_date: str | None = None   # API v1.4 대비
    retest_date: str | None = None   # PR #5 요청 (서버 날짜 충돌 탐지용, 현재 서버는 무시)
    items: list[Item] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
