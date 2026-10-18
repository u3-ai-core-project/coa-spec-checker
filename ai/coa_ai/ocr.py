"""[담당: 고도영] 스캔본·이미지 → Page (RapidOCR, PP-OCRv6 small ONNX).

엔진과 설정은 모델 테스트(ai/bench/README.md) 결과로 골랐다: Docker CPU 장당 약 3초, 152장 항목 인식률 90.8%.
OCR 글줄을 텍스트 PDF 와 같은 Page 로 바꿔 두면 머리글·표 복원·정규화 규칙을 그대로 쓴다.
"""
from __future__ import annotations

import math
import statistics
import threading
from pathlib import Path

import pymupdf

from coa_ai.models import Box, Line, Page, Word

RENDER_DPI = 200  # 글자 없는 PDF 쪽을 이 해상도로 그려서 OCR 한다 (모델 테스트 원본 단계와 같음)
A4_WIDTH_INCH = 8.27  # 해상도 정보가 없는 이미지는 쪽 폭을 A4 로 보고 dpi 를 추정한다
SHRINK = 0.1  # 검출 상자를 글줄 높이의 10% 줄인다 (PP-OCR 검출기가 상자를 부풀려 '번호' 열과 항목명이 붙는다)

_engine = None
_lock = threading.Lock()  # 백엔드는 문서를 백그라운드 스레드에서 처리하므로 엔진 하나를 번갈아 쓴다


class ImageOpenError(Exception):
    """이미지 파일을 열 수 없음."""


def read_image(path: str | Path) -> Page:
    """이미지 파일(PNG·JPG 등) 1장을 OCR 로 읽는다."""
    try:
        pix = pymupdf.Pixmap(str(path))
    except Exception as e:
        raise ImageOpenError(str(e)) from e
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):  # CMYK·색 팔레트 등은 RGB 로
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    return _ocr(pix, estimate_dpi(pix.width), page_no=1)


def read_pdf_page(path: str | Path, page_no: int) -> Page:
    """PDF 의 한 쪽(1부터)을 RENDER_DPI 로 그려 OCR 로 읽는다. 글자 층이 없는 스캔본 쪽에 쓴다."""
    with pymupdf.open(path) as doc:
        pix = doc[page_no - 1].get_pixmap(dpi=RENDER_DPI)
    return _ocr(pix, RENDER_DPI, page_no=page_no)


def estimate_dpi(width_px: int) -> float:
    """규칙은 글자 크기를 pt 로 판단하므로, 쪽 폭을 A4 로 보고 픽셀 → pt 비율을 정한다."""
    return width_px / A4_WIDTH_INCH


def _ocr(pix: pymupdf.Pixmap, dpi: float, page_no: int) -> Page:
    with _lock:
        res = load_engine()(pix.tobytes("png"))
    boxes = [] if res.boxes is None else [[(float(x), float(y)) for x, y in b] for b in res.boxes]
    page = ocr_to_page([shrink_box(b, SHRINK) for b in boxes], list(res.txts or []), dpi,
                       size_px=(pix.width, pix.height), page_no=page_no)
    page.ocr = True
    return page


def load_engine():
    """RapidOCR 엔진(한 번만 만든다). 처음 부르면 모델 파일을 내려받으므로 Docker 이미지를 만들 때 미리 불러 두면 좋다."""
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        # 글줄 방향 분류는 끈다: 켜 두면 바로 선 '=<5 ppm' 을 뒤집어 'udd g>=' 로 읽는 일이 있다
        # 스레드 기본값(코어 수)은 M4·Docker 에서 서로 밀려 2~3배 느렸다
        _engine = RapidOCR(params={"Global.use_cls": False, "Global.log_level": "warning",
                                   "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                                   "EngineConfig.onnxruntime.inter_op_num_threads": 1})
    return _engine


def shrink_box(box: list[tuple[float, float]], ratio: float) -> list[tuple[float, float]]:
    """네 꼭짓점을 상자 중심 쪽으로 가로·세로 (글줄 높이 × ratio) 만큼 당긴다."""
    s = ratio * math.dist(box[1], box[2])
    cx = sum(p[0] for p in box) / 4
    cy = sum(p[1] for p in box) / 4
    return [(x + (s if x < cx else -s), y + (s if y < cy else -s)) for x, y in box]


def ocr_to_page(boxes: list[list[tuple[float, float]]], texts: list[str], dpi: float, *,
                size_px: tuple[int, int] | None = None, page_no: int = 1, angle: float | None = None) -> Page:
    """OCR 글줄(네 꼭짓점 픽셀 좌표 + 글) → Page. 좌표는 pt 로 바꾼다.

    기울어진 스캔은 글줄 기울기 중앙값만큼 쪽 가운데를 기준으로 되돌리고, 그 각도를 Page.skew 에 남긴다.
    size_px: 이미지 크기. 주면 쪽 크기로 쓰고, 없으면(모델 테스트의 다른 엔진) 글줄을 감싸는 크기로 둔다.
    angle: 주면(라디안) 상자 모양 대신 그 값을 기울기로 쓴다.
    """
    k = 72 / dpi
    if angle is None:
        angles = [math.atan2(b[1][1] - b[0][1], b[1][0] - b[0][0]) for b in boxes
                  if math.dist(b[0], b[1]) > 3 * math.dist(b[1], b[2])]
        angle = statistics.median(angles) if angles else 0.0
    cx, cy = (size_px[0] / 2, size_px[1] / 2) if size_px else (0.0, 0.0)
    cos, sin = math.cos(-angle), math.sin(-angle)

    segs = []
    for b, text in zip(boxes, texts):
        text = text.strip()
        if not text:
            continue
        pts = [((cx + (x - cx) * cos - (y - cy) * sin) * k, (cy + (x - cx) * sin + (y - cy) * cos) * k) for x, y in b]
        segs.append((Box(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)),
                     text))
    if size_px:
        width, height = size_px[0] * k, size_px[1] * k
    elif segs:
        width, height = max(b.x1 for b, _ in segs) + 20, max(b.y1 for b, _ in segs) + 20
    else:
        width, height = 1, 1

    # 세로 중심이 가까운 글줄끼리 한 줄로 묶는다
    groups: list[list[tuple[Box, str]]] = []
    for box, text in sorted(segs, key=lambda s: s[0].cy):
        for g in groups:
            gh = statistics.median(b.height for b, _ in g)
            gcy = statistics.median(b.cy for b, _ in g)
            if abs(box.cy - gcy) <= 0.45 * min(gh, box.height):
                g.append((box, text))
                break
        else:
            groups.append([(box, text)])

    lines = []
    for g in groups:
        size = 0.75 * statistics.median(b.height for b, _ in g)
        words = []
        for box, text in sorted(g, key=lambda s: s[0].x0):
            words.extend(split_words(box, text, size))
        base = statistics.median(b.y1 for b, _ in g) - 0.2 * statistics.median(b.height for b, _ in g)
        lines.append(Line(words=words, page=page_no, baseline=base, size=size))
    lines.sort(key=lambda ln: (ln.baseline, ln.words[0].box.x0))
    return Page(number=page_no, width=width, height=height, lines=lines, skew=angle if size_px else 0.0)


def split_words(box: Box, text: str, size: float) -> list[Word]:
    """OCR 글줄 하나를 공백에서 나누고, 글자 수에 비례해 x 구간을 나눠 준다."""
    parts = text.split()
    total = len(text)
    out, pos = [], 0
    for part in parts:
        start = text.index(part, pos)
        end = start + len(part)
        x0 = box.x0 + box.width * start / total
        x1 = box.x0 + box.width * end / total
        out.append(Word(text=part, box=Box(x0, box.y0, x1, box.y1), size=size))
        pos = end
    return out
