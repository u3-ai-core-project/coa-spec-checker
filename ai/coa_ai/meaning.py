"""[담당: 고도영] 결과 칸 의미 분류 (기획안 v2 ★3 결과 의미 보조).

결과 칸 원문이 무엇을 말하는지 종류와 근거 한 줄을 붙인다. 판정(합격·불합격)은 서버가 한다.
  number      숫자 결과                       "12 ppm"
  bound       부등호 결과                     "< 10 ppm", "10 ppm 미만"
  nd          검출 안 됨                      "ND", "BDL", "未检出"
  spec_copy   결과 칸에 규격 조건을 다시 적음   결과 "Max 20 ppm", 규격 "≤ 20 ppm"
  pass_text   합격·적합 문구                  "Conforms", "合格"
  description 서술                           "White powder"

역할 분담 (모델 테스트 ai/bench/llm 결과)
  - 부등호 단어(max, NMT, 이하, 不大于 …)와 검출 안 됨 표기는 아래 규칙 표가 읽는다. LLM 은 이 대응을 틀렸다
    (Gemma 는 "max" 를 ">=" 로 바꿨다).
  - 규격 복사 여부는 코드가 부등호·숫자·단위를 비교해 정한다.
  - LLM 은 규칙이 못 읽은 칸만 본다. 숫자는 원문에 글자 그대로 있어야 받아들이고, LLM 답으로는 spec_copy 를 만들지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = ("number", "bound", "nd", "spec_copy", "pass_text", "description")
KIND_KO = {"number": "숫자 결과", "bound": "부등호 결과", "nd": "검출 안 됨", "spec_copy": "규격 문구 복사",
           "pass_text": "합격 문구", "description": "서술"}

_NUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_UNUM = r"(?:\d+(?:\.\d+)?|\.\d+)"
_UNIT = r"[%A-Za-zμµ][%A-Za-zμµ/]*"
_VALUE = re.compile(rf"^(?P<op><=|>=|<|>)?\s*(?P<num>{_NUM})\s*(?P<unit>{_UNIT})?$")  # 서버 value_parser 와 같음
_RANGE = re.compile(rf"^(?P<lo>{_UNUM})\s*(?:-|–|—|~|～|〜|to)\s*(?P<hi>{_UNUM})\s*(?P<unit>{_UNIT})?$", re.I)
_TAIL_NOTE = re.compile(r"^(?P<body>.*\d[^()（）]*?)\s*[(（][^()（）]*[)）]\s*$")  # "99.62 % (dry basis)"

# 검출 안 됨: 서버 규칙(_ND)에 BDL·LOD·중국어·한국어 표기를 더했다
_ND = re.compile(
    r"(?<![a-z])n\.?\s?d\.?(?![a-z])|none\s+detected|not\s+detected|below\s+(?:the\s+)?detection\s+limit"
    r"|(?<![a-z])bdl(?![a-z])|<\s*lo[dq](?![a-z])|未检出|不得检出|검출\s*안\s*됨|검출되지\s*않|불검출|미검출"
    r"|검출\s*한계\s*미만",
    re.I,
)
# 부등호 단어 표. 긴 말을 먼저 본다 ("not more than" 이 "more than" 보다 먼저)
_PREFIX_OPS = [
    (r"not\s+more\s+than|nmt|max(?:imum)?\.?|不大于|不超过", "<="),
    (r"not\s+less\s+than|nlt|min(?:imum)?\.?|不小于|不低于", ">="),
    (r"less\s+than|below|小于|低于", "<"),
    (r"more\s+than|greater\s+than|above|大于|高于", ">"),
]
_SUFFIX_OPS = [(r"max(?:imum)?\.?|이하", "<="), (r"min(?:imum)?\.?|이상", ">="), (r"미만", "<"), (r"초과", ">")]
_OP_EVIDENCE = re.compile(
    r"[<>≤≥≦≧＜＞]|max|min|nmt|nlt|less|more|below|above|greater|이하|미만|이상|초과|不大于|不小于|小于|大于|不超过|低于|高于",
    re.I,
)
_PASS = re.compile(
    r"conform|complies|compliant|(?<![a-z])pass(?:ed|es)?(?![a-z])|meets|as\s+per\s+spec|within\s+spec"
    r"|符合|合格|적합|합격|이상\s*없음",
    re.I,
)

MEANING_SYSTEM = """너는 CoA 결과 칸의 원문이 어떤 종류인지 분류한다. 규격 충족 여부(합격·불합격)는 판단하지 않는다.
종류:
- number: 측정값 숫자 (예: "12 ppm", "99.6 %")
- bound: 측정 결과를 부등호나 '미만·이하'로 보고한 것 (예: "< 1")
- nd: 검출 안 됨 (예: "ND", "not detected")
- pass_text: 합격·적합·규격 충족을 말하는 문구
- description: 색·형태 등 서술
number 에는 원문에 적힌 숫자를 글자 그대로 옮긴다. 숫자가 없으면 "".
JSON 으로만 답한다. reason 에는 판단 근거를 한 줄로 쓴다."""


@dataclass(frozen=True)
class ValueMeaning:
    kind: str | None
    reason: str | None


@dataclass(frozen=True)
class Condition:
    """칸 원문을 읽은 결과. kind: value(부등호 + 숫자) | range(lo~hi) | nd"""
    kind: str
    op: str | None
    num: float | None
    unit: str | None
    hi: float | None


def _normalize(s: str) -> str:
    """서버 value_parser._normalize_text 와 같은 표기 정리."""
    s = s.strip()
    s = (s.replace("＜", "<").replace("＞", ">").replace("≦", "<=").replace("≤", "<=")
          .replace("≧", ">=").replace("≥", ">=").replace("=<", "<=").replace("=>", ">="))
    s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)
    s = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", s)
    return s


def _key(s: str) -> str:
    """서버 is_spec_text_as_result 와 같은 비교 키."""
    return re.sub(r"\s+", "", _normalize(s)).casefold()


def _unit(u: str | None) -> str | None:
    return u.lower().replace("μ", "u").replace("µ", "u") if u else None


def _value(text: str, op: str | None = None) -> Condition | None:
    m = _VALUE.match(text.strip())
    if not m or (op and m["op"]):
        return None
    return Condition("value", op or m["op"] or "=", float(m["num"]), _unit(m["unit"]), None)


def parse_condition(text: str) -> Condition | None:
    """칸 원문 → Condition. 규칙으로 못 읽으면 None."""
    t = _normalize(text)
    if _ND.search(t):
        return Condition("nd", None, None, None, None)
    m = _TAIL_NOTE.match(t)
    if m:
        t = m["body"].strip()
    m = _RANGE.match(t)
    if m:
        return Condition("range", None, float(m["lo"]), _unit(m["unit"]), float(m["hi"]))
    for words, op in _PREFIX_OPS:
        m = re.match(rf"^(?:{words})\s*:?\s*(?P<rest>.+)$", t, re.I)
        if m:
            return _value(m["rest"], op)
    for words, op in _SUFFIX_OPS:
        m = re.match(rf"^(?P<rest>.+?)\s*(?:{words})$", t, re.I)
        if m:
            return _value(m["rest"], op)
    return _value(t)


def _fmt(c: Condition) -> str:
    unit = f" {c.unit}" if c.unit else ""
    if c.kind == "range":
        return f"{c.num:g} – {c.hi:g}{unit}"
    return f"{c.op} {c.num:g}{unit}" if c.op != "=" else f"{c.num:g}{unit}"


def _same_unit(a: Condition, b: Condition) -> bool:
    return not a.unit or not b.unit or a.unit == b.unit


def classify(raw_value: str | None, raw_spec: str | None, llm=None, *, raw_name: str | None = None) -> ValueMeaning:
    """결과 칸 원문의 종류와 근거. llm(coa_ai.llm.LLMClient)이 없으면 규칙만 쓴다."""
    if raw_value is None or not raw_value.strip():
        return ValueMeaning(None, None)
    value = raw_value.strip()
    spec = (raw_spec or "").strip() or None
    has_digit = bool(re.search(r"\d", value))

    if spec and has_digit and _key(value) == _key(spec):
        return ValueMeaning("spec_copy", f"결과 칸이 규격 칸과 같은 글({spec})")

    pv = parse_condition(value)
    if pv is not None:
        ps = parse_condition(spec) if spec else None
        if pv.kind == "nd":
            return ValueMeaning("nd", f"검출 안 됨 표기({value})")
        if pv.kind == "range":
            if ps and ps.kind == "range" and (ps.num, ps.hi) == (pv.num, pv.hi) and _same_unit(pv, ps):
                return ValueMeaning("spec_copy", f"규격 칸과 같은 범위({_fmt(ps)})를 결과 칸에 다시 적음")
            return ValueMeaning(None, f"범위로 적힌 결과({value})")
        if pv.op == "=":
            return ValueMeaning("number", f"숫자 결과({_fmt(pv)})")
        if ps and ps.kind == "value" and (ps.op, ps.num) == (pv.op, pv.num) and _same_unit(pv, ps):
            return ValueMeaning("spec_copy", f"규격 칸과 같은 조건({_fmt(ps)})을 결과 칸에 다시 적음")
        other = f", 규격 조건({_fmt(ps)})과 다름" if ps and ps.kind == "value" else ""
        return ValueMeaning("bound", f"부등호 결과({_fmt(pv)}){other}")

    if not has_digit:
        if _PASS.search(value):
            return ValueMeaning("pass_text", f"합격 문구({value})")
        asked = _ask_llm(llm, value, spec, raw_name, ["pass_text", "description"])
        if asked:
            return asked
        return ValueMeaning("description", "숫자 없는 서술")

    asked = _ask_llm(llm, value, spec, raw_name, ["number", "bound", "nd", "pass_text", "description"])
    return asked or ValueMeaning(None, f"규칙으로 읽지 못한 표기({value})")


def _ask_llm(llm, value: str, spec: str | None, raw_name: str | None, kinds: list[str]) -> ValueMeaning | None:
    if llm is None:
        return None
    props = {"kind": {"type": "string", "enum": kinds}, "reason": {"type": "string"}}
    needs_number = "number" in kinds
    if needs_number:
        props["number"] = {"type": "string"}
    schema = {"type": "object", "properties": props, "required": list(props)}
    user = f"항목명: {raw_name or '(없음)'}\n결과 칸: {value}\n규격 칸: {spec or '(없음)'}"
    answer = llm.json_chat(MEANING_SYSTEM, user, schema, max_tokens=160)
    if not answer or answer.get("kind") not in kinds:
        return None
    kind = answer["kind"]
    if kind in ("number", "bound"):
        num = str(answer.get("number") or "").strip()
        if not num or (num not in value and num not in _normalize(value)):
            return None  # 원문에 없는 숫자
        if kind == "bound" and not _OP_EVIDENCE.search(value):
            return None  # 부등호 근거가 원문에 없음
    reason = str(answer.get("reason") or "").strip() or KIND_KO[kind]
    return ValueMeaning(kind, f"AI 판단: {reason}")
