"""[담당: 고도영] 시험 항목 표 복원 (특정 양식에 묶이지 않는 범용 규칙).

1. 머리글 띠 찾기: 열 역할 키워드(항목·결과·규격·단위·Min·Max·방법·판정·번호)가 2칸 이상인 줄.
   위아래로 붙은 2단 머리글(중·영)은 합친다.
2. 열 구간: 머리글 아래 줄들의 단어가 비어 있는 세로 띠를 열 경계로 본다.
   머리글이 열 가운데에 있고 값이 왼쪽에서 시작하는 양식(가상 A·B)도 이 방식이면 맞는다.
3. 행: 항목 열에 글자가 있는 줄을 행 기준점으로 삼고, 나머지 칸은 세로로 가장 가까운 기준점에 붙인다.
   위아래로 나뉜 칸(가상 D 'White crystalline / powder', 가상 B 외관 규격)도 한 행으로 모인다.
4. 머리글이 없는 문서는 '이름  값' 목록(Alfa 13418)과 '기호 값' 격자(Puratronic)를 대신 읽는다.

값은 해석하지 않고 원문 그대로 둔다 (값 해석은 서버 담당).
"""
from __future__ import annotations

import difflib
import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from coa_ai.models import Box, Line, Page, RawRow, Word
from coa_ai.normalize import ELEMENTS
from coa_ai.pdf_text import phrases

CONF_CLEAN = 0.95    # 머리글이 있는 표에서 깨끗하게 읽은 행
CONF_FIXED = 0.85    # 칸 보정이 들어간 행
CONF_LIST = 0.7      # 머리글 없는 목록·격자

# 열 역할 키워드 (공백을 뺀 소문자로 비교). 긴 것부터 비교한다.
ROLE_WORDS: dict[str, list[str]] = {
    "item": ["resultname", "testitems", "testitem", "itemtest", "testparameter", "parameters", "parameter",
             "characteristics", "characteristic", "analyte", "items", "item", "tests", "test",
             "检验项目", "检测项目", "项目", "시험항목", "항목"],
    "result": ["testvalue", "testresults", "testresult", "results", "result", "found", "actual", "value",
               "检验结果", "检测结果", "结果", "시험결과", "결과"],
    "spec": ["specifications", "specification", "specs", "spec", "limits", "limit", "requirements", "requirement",
             "standard", "标准要求", "技术要求", "标准", "指标", "규격", "기준"],
    "unit": ["units", "unit", "uom", "单位", "단위"],
    "min": ["minimum", "min.", "min", "lsl"],
    "max": ["maximum", "max.", "max", "usl"],
    "method": ["testmethod", "methods", "method", "检验方法", "方法", "시험방법"],
    "judge": ["judgement", "judgment", "status", "verdict", "pass/fail", "单项判定", "判定", "판정"],
    "no": ["sr.no.", "srno", "no.", "no", "#", "序号", "번호"],
}
_VALUE_ROLES = {"result", "spec", "min", "max"}

# 표가 끝났다고 보는 줄 (공백 뺀 소문자의 시작 부분)
_STOP_WORDS = ("notes", "note:", "remark", "conclusion", "备注", "检验结论", "结论", "검사결과", "결론", "비고",
               "result:", "thebatch", "thisdocument", "thisistocertify", "theundersigned", "wehereby",
               "approvedby", "checkedby", "inspector", "signature", "dateofrelease", "certifiedby",
               "testby", "testedby", "issued:", "page", "companyaddress", "filelocation", "electronically",
               "productsareprocessed", "referenceorstandard", "检验员", "审核", "批准")

_UNIT_RE = re.compile(
    # '% ww'·'% wiw'·'mgkg' 는 스캔본 OCR 이 '% w/w'·'mg/kg' 의 빗금을 놓치거나 i 로 읽은 것
    r"^(%|%\s*w[/il1|]{0,2}w|w/w\s*%|wt\s*%|w/w|ppm|ppb|ppt|mg\s*/?\s*kg|mg/l|g/kg|g/l|μg/kg|µg/kg|ug/kg|μg/g|µg/g|ug/g|"
    r"μm|µm|um|nm|mm|g/ml|g/cm3|g/cm³|kg/m3|°c|ºc|℃|mpa·s|ms/cm|μs/cm|ph|—|–|-|n/a|na|%\(m/m\)|mass%)$",
    re.IGNORECASE)
_NUMERIC_RE = re.compile(r"^[<>≤≥=＜＞]{0,2}\s*[-+]?\d+(?:[.,]\d+)?\s*(?:[%a-zA-Zμµ/°º℃]+)?$")
_VALUE_LIKE_RE = re.compile(
    r"^(?:(?:[<>≤≥＜＞]=?|=<|=>|<=|>=)\s*)?[-+]?\d+(?:[.,]\d+)?\s*(?:%|ppm|ppb|mg/kg|μg/kg|µg/kg|ug/kg|μg/g|µg/g|"
    r"ug/g|g/kg|wt\s*%|μm|µm|um)?\s*(?:\(.*\))?$"
    r"|^(?:nd|n\.d\.?|none\s+detected|not\s+detected|passes(?:\s+test)?|pass|conforms|complies|符合|合格|적합|불검출)$",
    re.IGNORECASE)
_HIDDEN_NAME_RE = re.compile(r"^Type:\s*(?P<analyte>.+?)\s+measure\b\s*(?P<rest>.*)$", re.IGNORECASE)
_SPACED_CAPS_RE = re.compile(r"^(?:[A-Z]{1,3}\s)+[A-Z]{1,3}$")  # 'A S S AY', 'T R A C E M E TA L S'
_SYMBOL_RE = re.compile(r"^[A-Z][a-z]?$")
_CJK_ONLY = re.compile(r"^[一-鿿]+$")
_ROW_NO_RE = re.compile(r"^\d{1,3}[.)]?$")
_GRID_OPS = {"<", ">", "≤", "≥", "<=", ">=", "=<", "=>", "＜", "＞"}
GRID_MIN_PAIRS = 3  # 기호·값 짝이 이만큼 있는 줄은 앞뒤 줄 없이 혼자서도 격자로 본다


def compact(text: str) -> str:
    """비교용: 호환 문자 정리(NFKC) → 소문자 → 공백 제거."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def role_of(text: str) -> str | None:
    """머리글 칸 글자가 어떤 열 역할인지. 'Result name' 은 항목, 'Test Value' 는 결과."""
    c = compact(text).strip(":：")
    if not c or len(c) > 24:
        return None
    for role, words in ROLE_WORDS.items():
        if c in words:
            return role
    # 중·영 병기 칸('检验项目Test Item')이나 오타('Sepecification'), 스캔본 오독('Resuft', '检胎结果')
    best, best_score = None, 0.0
    cjk = bool(_CJK_ONLY.match(c))
    for role, words in ROLE_WORDS.items():
        for w in words:
            long_enough = len(w) >= 4 or (cjk and len(w) >= 2 and _CJK_ONLY.match(w))  # 한자는 두 글자로도 뜻이 선다
            if long_enough and (c.startswith(w) or c.endswith(w)) and len(w) >= len(c) * 0.4:
                score = len(w) / len(c)
            elif len(w) >= 6 and len(c) >= 6:
                score = difflib.SequenceMatcher(None, c, w).ratio()
                if score < 0.8:
                    continue
            else:
                continue
            if score > best_score:
                best, best_score = role, score
    return best


# ---------------------------------------------------------------------------
# 머리글 띠
# ---------------------------------------------------------------------------
@dataclass
class Header:
    first: int  # 머리글 첫 줄 번호
    last: int   # 머리글 끝 줄 번호
    cells: list[tuple[str, Box]] = field(default_factory=list)  # (역할, 위치)

    @property
    def roles(self) -> set[str]:
        return {r for r, _ in self.cells}


def _header_cells(line: Line, index: int) -> list[tuple[str, Box]]:
    cells = []
    for ph in phrases(line, index):
        role = role_of(ph.text)
        if role:
            cells.append((role, ph.box))
    return cells


def _is_header(cells: list[tuple[str, Box]]) -> bool:
    roles = {r for r, _ in cells}
    return len(roles) >= 2 and bool(roles & _VALUE_ROLES) and bool(roles & {"item", "unit", "method", "no"})


def find_headers(lines: list[Line]) -> list[Header]:
    out: list[Header] = []
    i = 0
    while i < len(lines):
        cells = _header_cells(lines[i], i)
        if not _is_header(cells):
            i += 1
            continue
        h = Header(first=i, last=i, cells=list(cells))
        # 바로 아래 줄도 머리글이면(중·영 2단) 합친다
        while h.last + 1 < len(lines):
            nxt = lines[h.last + 1]
            more = _header_cells(nxt, h.last + 1)
            gap = nxt.baseline - lines[h.last].baseline
            if gap <= 1.8 * max(nxt.size, lines[h.last].size) and len({r for r, _ in more}) >= 2:
                h.cells.extend(more)
                h.last += 1
            else:
                break
        out.append(h)
        i = h.last + 1
    return out


# ---------------------------------------------------------------------------
# 열 구간
# ---------------------------------------------------------------------------
@dataclass
class Column:
    role: str | None
    x0: float
    x1: float


def _is_stop(line: Line) -> bool:
    c = compact(line.text)
    return c.startswith(_STOP_WORDS)


def _region(lines: list[Line], start: int) -> tuple[list[int], float]:
    """머리글 아래에서 표에 속하는 줄 번호들과 행 간격(pitch)."""
    idx: list[int] = []
    gaps: list[float] = []
    prev = None
    for i in range(start, len(lines)):
        ln = lines[i]
        if _is_stop(ln):
            break
        if prev is not None:
            gap = ln.baseline - lines[prev].baseline
            pitch = statistics.median(gaps) if len(gaps) >= 2 else 2.0 * ln.size
            if gap > 2.2 * pitch and len(idx) >= 2:
                break
            if gap >= 1.0 * ln.size:  # 한 행 안의 여러 줄(위아래로 나뉜 칸)은 행 간격에서 뺀다
                gaps.append(gap)
        idx.append(i)
        prev = i
    pitch = statistics.median(gaps) if gaps else 2.0 * (lines[idx[0]].size if idx else 10.0)
    return idx, pitch


def _columns(lines: list[Line], idx: list[int], header: Header) -> list[Column]:
    """단어가 비어 있는 세로 띠로 열을 나누고, 겹치는 머리글 칸으로 역할을 붙인다."""
    words = [w for i in idx for w in lines[i].words]
    if not words:
        return []
    boxes = [w.box for w in words] + [box for _, box in header.cells]
    lo = int(min(b.x0 for b in boxes)) - 1
    hi = int(max(b.x1 for b in boxes)) + 2
    cover = [0] * (hi - lo)
    for i in idx:
        seen = set()
        for w in lines[i].words:
            for x in range(int(w.box.x0) - lo, int(w.box.x1) - lo + 1):
                seen.add(x)
        for x in seen:
            cover[x] += 1
    limit = max(1, int(len(idx) * 0.1))  # 10% 이하 줄만 걸친 띠는 빈 띠로 본다
    # 머리글 칸 아래는 값이 몇 줄뿐이어도 열로 남긴다 (순도 행에만 값이 있는 Min 열 등)
    for _, box in header.cells:
        for x in range(int(box.x0) - lo, int(box.x1) - lo + 1):
            cover[x] += limit + 1
    blocks: list[list[float]] = []
    for x, n in enumerate(cover):
        if n > limit:
            if blocks and x - blocks[-1][1] <= 3:
                blocks[-1][1] = x + 1
            else:
                blocks.append([x, x + 1])
    cols = [Column(None, b[0] + lo, b[1] + lo) for b in blocks]

    # 머리글에서 항목 열 제목만 빠진 경우(흐린 스캔본이 'Parameter' 를 놓침): 머리글 칸들보다 왼쪽 열이 항목명
    no_item_title = header.roles.isdisjoint({"item"})
    header_left = min(box.x0 for _, box in header.cells)
    for col in cols:
        overlaps = [(box.x_overlap(col.x0, col.x1), role) for role, box in header.cells]
        overlaps = [o for o in overlaps if o[0] > 0]
        if overlaps:
            col.role = max(overlaps)[1]
        elif no_item_title and col.x1 <= header_left:
            col.role = "item"
        else:
            mid = (col.x0 + col.x1) / 2
            near = min(header.cells, key=lambda rc: abs((rc[1].x0 + rc[1].x1) / 2 - mid))
            gap = max(near[1].x0 - col.x1, col.x0 - near[1].x1)
            col.role = near[0] if gap < 40 else None
    # 같은 역할이 이웃한 열로 쪼개졌으면 합친다
    merged: list[Column] = []
    for col in cols:
        if merged and merged[-1].role == col.role:
            merged[-1].x1 = col.x1
        else:
            merged.append(col)
    return merged


def _column_of(word: Word, cols: list[Column]) -> Column:
    best = max(cols, key=lambda c: word.box.x_overlap(c.x0, c.x1))
    if word.box.x_overlap(best.x0, best.x1) > 0:
        return best
    mid = (word.box.x0 + word.box.x1) / 2
    return min(cols, key=lambda c: min(abs(c.x0 - mid), abs(c.x1 - mid)))


# ---------------------------------------------------------------------------
# 행
# ---------------------------------------------------------------------------
@dataclass
class _Row:
    baseline: float
    cells: dict[str, list[tuple[float, Word]]] = field(default_factory=dict)
    fixed: bool = False

    def add(self, role: str, baseline: float, word: Word) -> None:
        self.cells.setdefault(role, []).append((baseline, word))

    def text(self, role: str) -> str | None:
        parts = self.cells.get(role)
        if not parts:
            return None
        parts = sorted(parts, key=lambda p: (round(p[0], 1), p[1].box.x0))
        return " ".join(w.text for _, w in parts).strip() or None

    def box(self, role: str) -> Box | None:
        parts = self.cells.get(role)
        return Box.around(w.box for _, w in parts) if parts else None

    def all_box(self) -> Box:
        return Box.around(w.box for parts in self.cells.values() for _, w in parts)


def _rows(lines: list[Line], idx: list[int], cols: list[Column], pitch: float) -> list[_Row]:
    split: list[tuple[float, dict[str, list[Word]]]] = []
    for i in idx:
        by_role: dict[str, list[Word]] = {}
        for w in lines[i].words:
            col = _column_of(w, cols)
            role = col.role
            if role == "no" and not _ROW_NO_RE.match(w.text):
                role = "item"  # 흐린 스캔본에서 번호와 왼쪽 정렬 항목명이 한 열로 붙음. 번호 열엔 숫자만 온다
            if role:
                by_role.setdefault(role, []).append(w)
        if by_role:
            split.append((lines[i].baseline, by_role))

    rows: list[_Row] = []
    for base, by_role in split:
        if "item" not in by_role:
            continue
        only_name = set(by_role) <= {"item", "no"}
        if only_name and rows and 0 < base - rows[-1].baseline < 0.7 * pitch and _has_values(rows[-1]):
            # 바로 위 행의 항목명이 다음 줄로 넘어간 경우
            for w in by_role["item"]:
                rows[-1].add("item", base, w)
            continue
        row = _Row(baseline=base)
        for role, ws in by_role.items():
            for w in ws:
                row.add(role, base, w)
        rows.append(row)

    # 항목 열이 빈 줄의 칸은 세로로 가장 가까운 행에 붙인다
    for base, by_role in split:
        if "item" in by_role or not rows:
            continue
        near = min(rows, key=lambda r: abs(r.baseline - base))
        if abs(near.baseline - base) > 0.75 * pitch:
            continue
        for role, ws in by_role.items():
            for w in ws:
                near.add(role, base, w)
    return rows


def _has_values(row: _Row) -> bool:
    return any(row.cells.get(r) for r in ("result", "spec", "min", "max", "unit"))


def _spec_from_min_max(lo: str | None, hi: str | None) -> str | None:
    """Min·Max 두 칸을 규격 문자열 하나로. 숫자가 아니면 원문을 그대로 잇는다."""
    if lo and hi and _NUMERIC_RE.match(lo) and _NUMERIC_RE.match(hi):
        return f"{lo} – {hi}"
    if hi and not lo and _NUMERIC_RE.match(hi):
        return f"≤ {hi}"
    if lo and not hi and _NUMERIC_RE.match(lo):
        return f"≥ {lo}"
    joined = " ".join(t for t in (lo, hi) if t)
    return joined or None


def _to_raw(row: _Row, page: int) -> RawRow | None:
    name = row.text("item")
    value = row.text("result")
    spec = row.text("spec")
    if spec is None and (row.cells.get("min") or row.cells.get("max")):
        spec = _spec_from_min_max(row.text("min"), row.text("max"))
        if spec and not spec.startswith(("≤", "≥")) and " – " not in spec:
            # 숫자가 아닌 규격 문구가 Min·Max 칸에 걸쳐 있으면 읽는 순서대로 다시 잇는다
            parts = sorted(row.cells.get("min", []) + row.cells.get("max", []),
                           key=lambda p: (round(p[0], 1), p[1].box.x0))
            spec = " ".join(w.text for _, w in parts)
    unit = row.text("unit")
    if not name:
        return None
    if value is None and spec is None:
        return None  # 구분 제목(ASSAY, ANIONS)이나 빈 행
    if _SPACED_CAPS_RE.match(name):
        return None
    fixed = row.fixed

    # 단위 열에 단위가 아닌 글자(넘친 항목명 '(as SO4)', 조건 'At 25°C')가 들어온 경우
    if unit and not _UNIT_RE.match(unit.strip()):
        name, unit, fixed = f"{name} {unit}", None, True
    if unit and unit.strip() in {"—", "–", "-", "n/a", "N/A"}:
        unit = None

    # 숨은 항목명: Fisher 양식 A 'Trace analysis | Type: Na measure < 10 ppm'
    for attr in ("spec", "value"):
        text = spec if attr == "spec" else value
        m = _HIDDEN_NAME_RE.match(text or "")
        if m:
            if "(Type:" not in name:
                name = f"{name} (Type: {m['analyte']} measure)"
            rest = m["rest"].strip() or None
            if attr == "spec":
                spec = rest
            else:
                value = rest

    if value in {"—", "–", "-"}:
        value = None
    if row.cells.get("result") and len({round(b, 1) for b, _ in row.cells["result"]}) > 1:
        fixed = True  # 결과 값이 여러 줄에 걸침
    return RawRow(page=page, name=name, value=value, spec=spec, unit=unit,
                  value_box=row.box("result"), row_box=row.all_box(),
                  confidence=CONF_FIXED if fixed else CONF_CLEAN)


# ---------------------------------------------------------------------------
# 머리글 없는 목록·격자
# ---------------------------------------------------------------------------
def _list_rows(page: Page) -> list[RawRow]:
    """'이름  값' 이 3줄 이상 같은 위치에 이어지는 목록, 또는 '기호 값' 이 반복되는 격자."""
    candidates: list[tuple[int, list[tuple[str, Box, str, Box]]]] = []
    for i, ln in enumerate(page.lines):
        ph = phrases(ln, i)
        grid = _grid_pairs(ln.words)
        pairs = grid if len(grid) >= 2 else []  # 격자를 먼저 본다 (스캔본은 구가 붙어 2개로 줄기도 한다)
        if not pairs and len(ph) == 2 and _is_name(ph[0].text) and _VALUE_LIKE_RE.match(ph[1].text.strip()):
            pairs = [(ph[0].text, ph[0].box, ph[1].text, ph[1].box)]
        candidates.append((i, pairs))

    # 같은 x 에서 시작하는 연속 줄 묶음 중 3줄 이상인 것만
    out: list[RawRow] = []
    run: list[list[tuple[str, Box, str, Box]]] = []

    def flush():
        if len(run) >= 3 or any(len(pairs) >= GRID_MIN_PAIRS for pairs in run):
            for pairs in run:
                for name, nbox, value, vbox in pairs:
                    out.append(RawRow(page=page.number, name=name, value=value, spec=None, unit=None,
                                      value_box=vbox, row_box=nbox.union(vbox), confidence=CONF_LIST))
        run.clear()

    for _, pairs in candidates:
        if pairs and (not run or abs(run[-1][0][1].x0 - pairs[0][1].x0) <= 4):
            run.append(pairs)
        else:
            flush()
            if pairs:
                run.append(pairs)
    flush()
    return out


_COLON_LINE_RE = re.compile(r"^(?P<label>[^:：]{2,40})[:：]\s*(?P<rest>\S.*)$")
_COLON_VALUE_RE = re.compile(
    r"^(?:(?:[<>≤≥＜＞]=?|=<|=>)\s*)?[-+]?\d+(?:[.,]\d+)?\s*(?:%|ppm|ppb|mg/kg)?(?:\s*\([^()]*\))?$", re.IGNORECASE)
_COLON_NOT_ITEM_RE = re.compile(r"\b(?:lot|batch|product|catalog|cat|order|cas|no|number)\b|iso\s*\d", re.IGNORECASE)
_COLON_TEXT_LABEL_RE = re.compile(r"^(?:appearance|外观|외관|성상)$", re.IGNORECASE)
_COLON_IMPURITY_RE = re.compile(r"^impurity(?:\s+content)?$", re.IGNORECASE)
COLON_MIN_LINES = 3  # '항목: 값' 줄이 이만큼 있는 쪽만 목록으로 본다


def _colon_rows(page: Page) -> list[RawRow]:
    """'항목: 값' 으로 한 줄씩 적은 목록 (Alfa·Thermo 의 짧은 CoA).

    'Assay: 57.0%', 'Chloride content: 34.2ppm', 'Insolubles: <0.1% (in Water)' 는 앞이 항목명, 뒤가 결과다.
    'Impurity content: 0.0001% Iron' 은 항목명이 값 뒤에 온다 ('(Fe)'·'(K+Na)' 의 괄호는 뗀다).
    값이 숫자로 시작하지 않는 줄(Product No.·Lot No.·Product)은 외관만 빼고 항목으로 보지 않는다.
    """
    rows: list[RawRow] = []
    for ln in page.lines:
        m = _COLON_LINE_RE.match(ln.text.strip())
        if not m:
            continue
        label, rest = re.sub(r"\s+", " ", m["label"]).strip(), m["rest"].strip()
        if _COLON_TEXT_LABEL_RE.match(label):
            name, value = label, rest
        elif _COLON_NOT_ITEM_RE.search(label):
            continue
        elif _COLON_IMPURITY_RE.match(label):
            vm = re.match(r"^(?P<value>(?:(?:[<>≤≥＜＞]=?|=<|=>)\s*)?[-+]?\d+(?:[.,]\d+)?\s*(?:%|ppm|ppb|mg/kg)?)\s*(?P<name>.+)$", rest)
            if not vm:
                continue
            name, value = vm["name"].strip().strip("()（）").strip(), vm["value"].strip()
            if not name:
                continue
        elif _COLON_VALUE_RE.match(rest):
            name, value = label, rest
        else:
            continue
        rows.append(RawRow(page=page.number, name=name, value=value, spec=None, unit=None,
                           value_box=ln.box, row_box=ln.box, confidence=CONF_LIST))
    return rows if len(rows) >= COLON_MIN_LINES else []


def _grid_symbol(text: str) -> str | None:
    """격자 칸의 원소 기호. OCR 이 소문자 l 을 대문자 I 로 읽은 것('TI', 'AI')은 고친다."""
    if _SYMBOL_RE.match(text) and text in ELEMENTS:
        return text
    if len(text) == 2 and text[1] == "I" and text[0].isupper() and text[0] + "l" in ELEMENTS:
        return text[0] + "l"
    return None


def _grid_pairs(words: list[Word]) -> list[tuple[str, Box, str, Box]]:
    """'기호 값 기호 값 …' 줄을 단어 단위로 짝짓는다. 구 단위로 나누면 스캔본에서 값과 다음 기호가
    한 구로 붙어('< 1 Cr') 줄 전체를 놓쳤다. 값이 아닌 칸('Li  Matrix')은 건너뛴다."""
    pairs = []
    i = 0
    while i < len(words):
        sym = _grid_symbol(words[i].text)
        if sym is None:
            i += 1
            continue
        j = i + 1
        if j < len(words) and words[j].text in _GRID_OPS:
            j += 1
        if j < len(words) and _VALUE_LIKE_RE.match(" ".join(w.text for w in words[i + 1:j + 1])):
            value_words = words[i + 1:j + 1]
            pairs.append((sym, words[i].box, " ".join(w.text for w in value_words),
                          Box.around(w.box for w in value_words)))
            i = j + 1
        else:
            i += 1
    return pairs


def _is_name(text: str) -> bool:
    t = text.strip()
    return bool(re.search(r"[A-Za-z가-힣一-鿿]", t)) and len(t) <= 40 and not t.endswith((":", "："))


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def parse_tables(pages: list[Page]) -> list[RawRow]:
    """모든 페이지의 시험 항목 행. 머리글 없는 다음 페이지는 앞 페이지 열 구간을 이어 쓴다."""
    out: list[RawRow] = []
    carry: tuple[list[Column], float] | None = None
    for page in pages:
        lines = page.lines
        rows: list[RawRow] = []
        for header in find_headers(lines):
            idx, pitch = _region(lines, header.last + 1)
            if not idx:
                continue
            cols = _columns(lines, idx, header)
            if not any(c.role == "item" for c in cols) or not any(c.role in _VALUE_ROLES for c in cols):
                continue
            found = [r for r in (_to_raw(row, page.number) for row in _rows(lines, idx, cols, pitch)) if r]
            if found:
                rows.extend(found)
                carry = (cols, pitch)
        if not rows and carry and lines:
            idx, _ = _region(lines, 0)
            rows = [r for r in (_to_raw(row, page.number) for row in _rows(lines, idx, *carry)) if r]
        if not rows:
            rows = _list_rows(page) or _colon_rows(page)
            carry = None if not rows else carry
        out.extend(rows)
    return out
