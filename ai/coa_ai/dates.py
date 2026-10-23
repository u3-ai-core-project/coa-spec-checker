"""[담당: 고도영] CoA 날짜 표기 → 'YYYY-MM-DD'.

지원: 2026-02-21, 2026/02/21, 2026年02月24日, 27-Dec-2025, 10/Mar/2026, 27 Dec 2025, Aug 19, 2025,
      03/07/2026·08-02-2013 (숫자만: 월/일/년으로 읽고, 앞 숫자가 12보다 크면 일/월/년)
월·연도만 있는 날짜(08-2025)는 날을 지어내지 않고 무시한다.
"""
from __future__ import annotations

import re
from datetime import date

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MON = r"(?P<mon>[A-Za-z]{3,9})\.?"

_PATTERNS = [
    re.compile(r"(?<![\d/.-])(?P<y>\d{4})(?P<sep>[-/.])(?P<m>\d{1,2})(?P=sep)(?P<d>\d{1,2})(?![\d/.-])"),
    re.compile(r"(?<!\d)(?P<y>\d{4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?"),
    re.compile(rf"(?<![\w])(?P<d>\d{{1,2}})[\s\-/.]+{_MON}[\s\-/.,]+(?P<y>\d{{4}})(?!\d)"),
    re.compile(rf"(?<![\w]){_MON}\s+(?P<d>\d{{1,2}}),?\s+(?P<y>\d{{4}})(?!\d)"),
    re.compile(r"(?<![\d/.-])(?P<a>\d{1,2})\s*(?P<sep>[-/.])\s*(?P<b>\d{1,2})\s*(?P=sep)\s*(?P<y>\d{4})(?!\d)"),
]


def _build(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _from_match(m: re.Match) -> str | None:
    g = m.groupdict()
    y = int(g["y"])
    if g.get("mon") is not None:
        month = _MONTHS.get(g["mon"][:4].lower().rstrip(".")) or _MONTHS.get(g["mon"][:3].lower())
        return _build(y, month, int(g["d"])) if month else None
    if g.get("a") is not None:
        a, b = int(g["a"]), int(g["b"])
        return _build(y, b, a) if a > 12 >= b else _build(y, a, b)
    return _build(y, int(g["m"]), int(g["d"]))


_GLUED = re.compile(r"(\d{1,2}([-/.])\d{1,2}\2\d{4}|\d{4}([-/.])\d{1,2}\3\d{1,2})/(?=\d)")


def find_dates(text: str) -> list[str]:
    """글에 나온 날짜를 나온 순서대로. 겹치는 후보는 먼저 시작하는(같으면 긴) 쪽을 쓴다."""
    # 스캔본 OCR 이 'a / b' 의 공백을 놓쳐 붙은 두 날짜('10/18/2025/10/19/2025')를 떼어 놓는다
    text = _GLUED.sub(r"\1 / ", text or "")
    matches = sorted(((m.start(), -m.end(), m) for pat in _PATTERNS for m in pat.finditer(text)),
                     key=lambda t: (t[0], t[1]))
    out: list[str] = []
    taken_until = -1
    for start, neg_end, m in matches:
        if start < taken_until:
            continue
        iso = _from_match(m)
        if iso:
            out.append(iso)
            taken_until = -neg_end
    return out


def parse_date(text: str) -> str | None:
    dates = find_dates(text)
    return dates[0] if dates else None
