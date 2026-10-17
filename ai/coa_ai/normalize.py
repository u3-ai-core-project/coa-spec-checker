"""[담당: 고도영] 항목명 정규화: CoA 원문 항목명 → 사내 표준 항목명(normalized_name).

먼저 맞는 단계에서 끝낸다.
  1. DB 매핑 사전(item_mappings, 담당자 수정 누적)과 원문이 같으면 그대로   → dictionary
  2. 사전 별칭 (괄호 밖 이름: 'Sodium (Na)' → sodium)                       → dictionary
  3. 규칙: 중금속, 입도 D10/D50/D90, 'Type: X measure', '(as X)', '(Na)',
     '钠Na' 처럼 한자·한글 이름 + 기호, 이름 전체가 화학식('Na₂O')          → dictionary
  4. 유사도 (6자 이상 별칭, 0.88 이상)                                       → ai, 신뢰도 상한 0.6
  5. 못 찾음: 원문 항목명 그대로                                            → ai, 신뢰도 상한 0.6

신뢰도 상한 0.6 은 서버 기준(0.8)보다 낮아서, 자동으로 확정하지 않고 담당자 확인으로 넘긴다.
'Heavy metals (as Pb)' 는 3단계에서 중금속으로 먼저 잡혀 Pb 로 가지 않는다.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

AI_CAP = 0.6  # 사전·규칙으로 확정하지 못한 매핑의 신뢰도 상한

_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_CJK = r"一-鿿㐀-䶿가-힣"
_PARTICLE_RE = re.compile(r"(?<![a-z0-9])d\s?(10|50|90)(?![0-9])")


@dataclass(frozen=True)
class Mapping:
    name: str
    source: str  # "dictionary" | "ai"
    cap: float   # 이 항목 신뢰도의 상한


@lru_cache
def load_vocab() -> dict:
    return json.loads(resources.files("coa_ai").joinpath("vocab.json").read_text(encoding="utf-8"))


def strip_charges(text: str) -> str:
    """이온 전하(²⁻, ⁻)는 지우고 아래 첨자 숫자는 보통 숫자로. 'SO₄²⁻' → 'SO4'"""
    text = "".join(c for c in text if c not in _SUPERSCRIPTS)
    return text.translate(_SUBSCRIPT_DIGITS)


def canon(text: str) -> str:
    """별칭 비교용 표기: 전하 제거 → NFKC → 소문자 → 따옴표·공백 정리."""
    t = unicodedata.normalize("NFKC", strip_charges(text)).casefold()
    t = t.replace("’", "'").replace("‘", "'")
    t = re.sub(r"\s+", " ", t).strip(" :：")
    return t


def _compact(text: str) -> str:
    return canon(text).replace(" ", "")


def _without_parens(text: str) -> str:
    return re.sub(r"[(（][^)）]*[)）]", " ", text)


def _formula_token(text: str) -> str:
    """'SO4 2-', 'Cl-', 'Na₂O' → 'SO4', 'Cl', 'Na2O' (대소문자는 그대로)."""
    t = strip_charges(text).strip()
    t = re.sub(r"\s*\d?[+\-−]$", "", t)  # 끝에 붙은 전하 표기
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))


class Normalizer:
    def __init__(self, material_code: str, mappings: dict[str, str] | None = None):
        material = (material_code or "").strip().upper()
        self.mappings = {k.strip(): v for k, v in (mappings or {}).items()}
        self.mappings_ci = {canon(k): v for k, v in self.mappings.items()}
        self.names: dict[str, str] = {}
        self.aliases: dict[str, str] = {}
        self.formulas: dict[str, str] = {}
        for code, item in load_vocab()["items"].items():
            allowed = item.get("materials")
            if allowed and material not in allowed:
                continue
            self.names[code] = item["name"]
            for a in item.get("aliases", []):
                self.aliases[canon(a)] = code
                self.aliases.setdefault(_compact(a), code)
            for f in item.get("formulas", []):
                self.formulas[f] = code
        self._fuzzy_keys = [a for a in self.aliases if len(a) >= 6]

    # ------------------------------------------------------------------
    def map(self, raw_name: str) -> Mapping:
        raw = (raw_name or "").strip()
        if raw in self.mappings:
            return Mapping(self.mappings[raw], "dictionary", 1.0)
        if canon(raw) in self.mappings_ci:
            return Mapping(self.mappings_ci[canon(raw)], "dictionary", 1.0)

        code = self._exact(raw) or self._rules(raw)
        if code:
            return Mapping(self.names[code], "dictionary", 1.0)

        base = canon(_without_parens(raw))
        close = difflib.get_close_matches(base, self._fuzzy_keys, n=1, cutoff=0.88) if len(base) >= 6 else []
        if close:
            return Mapping(self.names[self.aliases[close[0]]], "ai", AI_CAP)
        return Mapping(raw, "ai", AI_CAP)

    # ------------------------------------------------------------------
    def _alias(self, text: str) -> str | None:
        if not text or not text.strip():
            return None
        return self.aliases.get(canon(text)) or self.aliases.get(_compact(text))

    def _formula(self, text: str) -> str | None:
        return self.formulas.get(_formula_token(text)) if text else None

    def _resolve(self, token: str) -> str | None:
        return self._formula(token) or self._alias(token)

    def _exact(self, raw: str) -> str | None:
        """괄호 밖 이름이 별칭과 같으면. 'Sodium (Na)' → sodium, 'Appearance (Color)' → appearance"""
        heavy = self._heavy(raw)
        if heavy:
            return heavy
        return self._alias(raw) or self._alias(_without_parens(raw))

    def _heavy(self, raw: str) -> str | None:
        c = canon(raw)
        if ("heavy metal" in c or "重金属" in c or "중금속" in c) and "heavy_metals" in self.names:
            return "heavy_metals"
        return None

    def _rules(self, raw: str) -> str | None:
        c = canon(raw)

        # 입도 D10·D50·D90
        m = _PARTICLE_RE.search(c)
        if m and (c.strip() in {"d10", "d50", "d90"} or any(k in c for k in ("particle", "粒度", "입도", "psd", "size"))):
            code = f"d{m.group(1)}"
            if code in self.names:
                return code

        # Fisher 양식 A: 'Trace analysis (Type: Na measure)'
        m = re.search(r"type:\s*(.+?)\s+measure", raw, re.IGNORECASE)
        if m:
            return self._resolve(m.group(1))

        # '(as SO4)', '(as LiOH)'
        m = re.search(r"[(（]\s*as\s+([^)）]+)[)）]", raw, re.IGNORECASE)
        if m:
            code = self._resolve(m.group(1))
            if code:
                return code

        # 괄호 안 기호: 'Iron (Fe)', 'Chloride (Cl⁻)', '황 산 염(SO₄)'
        for inner in re.findall(r"[(（]([^)）]+)[)）]", raw):
            code = self._formula(inner)
            if code:
                return code

        # 한자·한글 이름 + 영문·기호: '钠Na', '外观Appearance', '酸不溶物Acid Insoluble'
        m = re.match(rf"^([{_CJK}\s]+?)\s*([A-Za-z].*)$", raw)
        if m:
            return self._alias(m.group(1)) or self._resolve(m.group(2))

        # 이름 전체가 화학식: 'Li₂CO₃', 'Na₂O', 'SO₄', 'Cl'
        return self._formula(raw)
