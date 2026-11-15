"""[담당: 고도영] PDF 글자 좌표 → 줄(Line), 칸 후보(Phrase).

PyMuPDF rawdict 로 글자 하나하나의 위치·크기·기준선을 읽어 줄을 다시 만든다.
- 기준선이 가까운 글자를 한 줄로 묶는다.
- 줄의 대표 크기보다 작고 기준선이 어긋난 숫자·부호는 아래·위 첨자로 보고 유니코드 첨자로 바꿔 끼운다.
  예) Alfa 13418 'Li CO' + 작은 '2', '3' → 'Li₂CO₃' / 가상 A 'SO' + 작은 '4', '2-' → 'SO₄²⁻'
- 공백 글자나 넓은 간격에서 단어를 나누고, 더 넓은 간격에서 칸 후보(Phrase)를 나눈다.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from coa_ai.models import Box, Line, Page, Phrase, Word

_SUB = str.maketrans("0123456789+-−", "₀₁₂₃₄₅₆₇₈₉₊₋₋")
_SUP = str.maketrans("0123456789+-−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻")
_SCRIPT_CHARS = set("0123456789+-−")

IMAGE_BODY_RATIO = 0.3  # 한 쪽에서 이미지 하나가 쪽 넓이의 이 비율 이상이면 본문이 스캔 이미지인 쪽으로 본다
BASE_TOL = 0.25    # 같은 줄로 볼 기준선 차이 (글자 크기 배수)
SMALL_RATIO = 0.8  # 줄 대표 크기의 이 비율 이하이면 첨자 후보
SCRIPT_SHIFT = 0.06  # 첨자로 볼 최소 기준선 차이 (글자 크기 배수)
WORD_GAP = 0.5     # 공백 글자가 없어도 이 간격(글자 크기 배수)보다 넓으면 단어를 나눈다
PHRASE_GAP = 1.0   # 단어 사이가 이 간격(글자 크기 배수)보다 넓으면 다른 칸으로 본다


class PdfOpenError(Exception):
    """열 수 없는 PDF (손상, 암호, PDF 아님)."""


@dataclass
class _Char:
    c: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    base: float
    script: str = ""  # "", "sub", "sup"

    @property
    def space(self) -> bool:
        return self.c.isspace()


def read_pages(path: str | Path) -> list[Page]:
    """PDF 의 모든 페이지를 줄 단위로 읽는다. 글자가 없는 페이지(스캔본)는 lines 가 빈 목록이다."""
    try:
        doc = pymupdf.open(path)
    except Exception as e:
        raise PdfOpenError(str(e)) from e
    with doc:
        if not doc.is_pdf:
            raise PdfOpenError("PDF 파일이 아님")
        if doc.needs_pass:
            raise PdfOpenError("암호가 걸린 PDF")
        return [
            Page(number=i, width=page.rect.width, height=page.rect.height, lines=build_lines(_read_chars(page), i))
            for i, page in enumerate(doc, start=1)
        ]


def image_body_pages(path: str | Path) -> set[int]:
    """글자 층은 있지만 본문 표가 큰 이미지(스캔)인 쪽 번호(1부터).

    Alfa·Thermo 의 일부 CoA 는 머리말·꼬리말만 글자이고 시험 항목 표는 이미지다. 글자가 있다고 OCR 을 건너뛰면
    표를 못 읽고 'CoA 가 아님'으로 실패한다. 실물 61쪽에서 이 비율은 본문 이미지 쪽 0.39~0.45, 글자 PDF 쪽 0.23 이하였다.
    """
    try:
        doc = pymupdf.open(path)
    except Exception:
        return set()
    found = set()
    with doc:
        for i, page in enumerate(doc, start=1):
            area = page.rect.width * page.rect.height
            if not area:
                continue
            for info in page.get_image_info():
                box = pymupdf.Rect(info["bbox"]) & page.rect
                if box.width * box.height / area >= IMAGE_BODY_RATIO:
                    found.add(i)
                    break
    return found


def _read_chars(page: pymupdf.Page) -> list[_Char]:
    out: list[_Char] = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            if abs(line["dir"][1]) > 0.1:  # 세로·회전 글자(워터마크 등)는 읽지 않는다
                continue
            for span in line["spans"]:
                for ch in span["chars"]:
                    x0, y0, x1, y1 = ch["bbox"]
                    out.append(_Char(ch["c"], x0, y0, x1, y1, span["size"], ch["origin"][1]))
    return out


# ---------------------------------------------------------------------------
# 줄 만들기
# ---------------------------------------------------------------------------
def _main(chars: list[_Char]) -> tuple[float, float]:
    """줄의 대표 (기준선, 크기). 공백·첨자처럼 작은 글자는 빼고 큰 글자들로 정한다."""
    glyphs = [c for c in chars if not c.space] or chars
    biggest = max(c.size for c in glyphs)
    main = [c for c in glyphs if c.size >= SMALL_RATIO * biggest]
    return statistics.median(c.base for c in main), statistics.median(c.size for c in main)


def _is_script_cluster(chars: list[_Char]) -> bool:
    glyphs = [c for c in chars if not c.space]
    return 0 < len(glyphs) <= 6 and all(c.c in _SCRIPT_CHARS for c in glyphs)


def build_lines(chars: list[_Char], page_no: int) -> list[Line]:
    if not any(not c.space for c in chars):
        return []

    # 1) 기준선이 가까운 글자끼리 묶는다
    clusters: list[list[_Char]] = []
    for ch in sorted(chars, key=lambda c: (c.base, c.x0)):
        if clusters:
            base, size = _main(clusters[-1])
            if abs(ch.base - base) <= BASE_TOL * max(ch.size, size):
                clusters[-1].append(ch)
                continue
        clusters.append([ch])
    clusters = [cl for cl in clusters if any(not c.space for c in cl)]

    # 2) 숫자·부호만 있는 작은 묶음은 옆 줄의 첨자로 합친다 (가상 A 의 '2-')
    keep: list[list[_Char]] = []
    scripts: list[list[_Char]] = []
    for cl in clusters:
        (scripts if _is_script_cluster(cl) else keep).append(cl)
    for cl in scripts:
        base, size = _main(cl)
        x0, x1 = min(c.x0 for c in cl), max(c.x1 for c in cl)
        best, best_d = None, None
        for other in keep:
            ob, osz = _main(other)
            if size > SMALL_RATIO * osz or not (ob - 0.8 * osz <= base <= ob + 0.5 * osz):
                continue
            ox0, ox1 = min(c.x0 for c in other), max(c.x1 for c in other)
            if x1 < ox0 - osz or x0 > ox1 + osz:
                continue
            d = abs(base - ob)
            if best_d is None or d < best_d:
                best, best_d = other, d
        if best is None:
            keep.append(cl)
            continue
        ob, _ = _main(best)
        for c in cl:
            c.script = "sup" if c.base < ob else "sub"
        best.extend(cl)

    # 3) 줄 안에서 첨자 표시 → 단어 나누기
    lines = []
    for cl in keep:
        base, size = _main(cl)
        for c in cl:
            if not c.script and not c.space and c.c in _SCRIPT_CHARS and c.size <= SMALL_RATIO * size:
                if abs(c.base - base) >= SCRIPT_SHIFT * size:
                    c.script = "sub" if c.base > base else "sup"
        words = _words(sorted(cl, key=lambda c: c.x0), size)
        if words:
            lines.append(Line(words=words, page=page_no, baseline=base, size=size))
    lines.sort(key=lambda ln: (ln.baseline, ln.words[0].box.x0))
    return lines


def _words(chars: list[_Char], size: float) -> list[Word]:
    words: list[Word] = []
    cur: list[_Char] = []

    def flush():
        if cur:
            text = "".join(c.c.translate(_SUB if c.script == "sub" else _SUP) if c.script else c.c for c in cur)
            box = Box(min(c.x0 for c in cur), min(c.y0 for c in cur), max(c.x1 for c in cur), max(c.y1 for c in cur))
            words.append(Word(text=text, box=box, size=size))
            cur.clear()

    for c in chars:
        if c.space:
            flush()
            continue
        if cur and not c.script and c.x0 - cur[-1].x1 > WORD_GAP * size:
            flush()
        cur.append(c)
    flush()
    return words


# ---------------------------------------------------------------------------
# 칸 후보
# ---------------------------------------------------------------------------
def phrases(line: Line, index: int) -> list[Phrase]:
    """줄을 넓은 간격 기준으로 나눈다. 표의 칸, 또는 '라벨  값' 의 양쪽이 된다."""
    out: list[Phrase] = []
    cur: list[Word] = [line.words[0]]
    for w in line.words[1:]:
        if w.box.x0 - cur[-1].box.x1 > PHRASE_GAP * line.size:
            out.append(Phrase(" ".join(x.text for x in cur), Box.around(x.box for x in cur), index))
            cur = []
        cur.append(w)
    out.append(Phrase(" ".join(x.text for x in cur), Box.around(x.box for x in cur), index))
    return out
