"""[담당: 고도영] 결과 의미 분류의 규칙 베이스라인.

서버 판정 규칙(PR #5 backend/app/services/judgement/value_parser.py, 담당 장수민)의
검출 안 됨 정규식·값 정규식·'결과 칸 = 규격 문구' 비교를 그대로 옮기고, 합격 문구 사전만 더했다.
"""
from __future__ import annotations

import re

_ND = re.compile(
    r"(?<![a-z])n\.?\s?d\.?(?![a-z])|none\s+detected|not\s+detected|검출\s*안\s*됨|검출되지\s*않|불검출|미검출",
    re.IGNORECASE,
)
_NUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_UNIT = r"[%A-Za-zμµ][%A-Za-zμµ/]*"
_VALUE = re.compile(rf"^(?P<op><=|>=|<|>)?\s*(?P<num>{_NUM})\s*(?P<unit>{_UNIT})?$")
_PASS = re.compile(r"conform|complies|pass|符合|合格|적합|합격", re.I)  # 베이스라인 사전 (기본 표기만)


def _normalize_text(s: str) -> str:
    s = s.strip()
    s = (s.replace("＜", "<").replace("＞", ">").replace("≦", "<=").replace("≤", "<=")
          .replace("≧", ">=").replace("≥", ">=").replace("=<", "<=").replace("=>", ">="))
    s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)
    s = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", s)
    return s


def _spec_key(s: str) -> str:
    return re.sub(r"\s+", "", _normalize_text(s)).casefold()


def kind(raw_value: str, raw_spec: str | None) -> str:
    if raw_spec and _spec_key(raw_value) == _spec_key(raw_spec):
        return "spec_copy"
    s = _normalize_text(raw_value)
    if _ND.search(s):
        return "nd"
    m = _VALUE.match(s)
    if m:
        return "bound" if m["op"] else "number"
    if not re.search(r"\d", s):
        return "pass_text" if _PASS.search(s) else "description"
    return "unknown"  # 서버는 '값 형식을 해석할 수 없음' → 확인 필요


def parse(s: str) -> tuple[str, str | None, float | None, str | None] | None:
    """규칙으로 읽히면 (종류, 부등호, 숫자, 단위). 못 읽으면 None (→ LLM 정규형)."""
    t = _normalize_text(s)
    if _ND.search(t):
        return ("nd", None, None, None)
    m = _VALUE.match(t)
    if m:
        return ("value", m["op"] or "=", float(m["num"]), (m["unit"] or "").lower() or None)
    return None
