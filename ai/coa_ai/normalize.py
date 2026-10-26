"""[담당: 고도영] 항목명 정규화: CoA 원문 항목명 → 사내 표준 항목명(normalized_name).

먼저 맞는 단계에서 끝낸다.
  1. DB 매핑 사전(item_mappings, 담당자 수정 누적)과 원문이 같으면 그대로   → dictionary
  2. 사전 별칭 (괄호 밖 이름: 'Sodium (Na)' → sodium)                       → dictionary
  3. 규칙: 중금속, 입도 D10/D50/D90/D99, 'Type: X measure', '(as X)', '(Na)',
     '钠Na' 처럼 한자·한글 이름 + 기호, 화학식·이름 + 함량('Li₂CO₃ 함량', 'K2O content'),
     이름 전체가 화학식('Na₂O')                                             → dictionary
     못 찾으면 스캔본(OCR) 잡음을 걷어 내고 한 번 더: 앞에 붙은 행 번호('4 钠Na'),
     첨자를 읽은 괄호·밑줄('Fe{2O3', 'Li2CO_3'), l·O 를 I·0 으로 읽은 기호('CI', 'S04'),
     한자·한글 이름 뒤에 붙은 잡음('钾κ', '水分1.0')
  4. 유사도 (6자 이상 별칭, 0.88 이상)                                       → ai, 신뢰도 상한 0.6
     스캔본 짐작: 앞 1~3 단어가 별칭과 같거나 비슷함(옆 칸 글자가 붙은 'Moisture % ww',
     오타 'Suffate'), 한자 원소명 뒤 기호를 비슷한 한자로 읽음('硼日'). 합산 줄('Na+K')은 짐작하지 않는다
  5. 이름 전체가 표준 목록 밖 원소 기호 하나('Ti', 'Co²⁺'): 원문 그대로        → ai, 신뢰도 상한 0.6
  6. LLM 제안 (llm 을 넘겼을 때만, 후보 목록 + '없음' 중 하나로 답을 강제)     → ai, 신뢰도 상한 0.6
     단, 다른 원자재 전용 항목의 별칭(수산화리튬의 'Assay')은 일부러 매핑하지 않은 것이라 묻지 않는다
  7. 못 찾음: 원문 항목명 그대로                                            → ai, 신뢰도 상한 0.6

신뢰도 상한 0.6 은 서버 기준(0.8)보다 낮아서, 자동으로 확정하지 않고 담당자 확인으로 넘긴다.
LLM 제안도 마찬가지라 잘못 제안해도 자동 확정되지 않는다. 담당자가 확정하면 서버가 매핑 사전에 쌓는다.
5단계는 LLM 이 목록 밖 원소(Ti, Co)를 비슷한 원소로 잘못 고르던 것(모델 테스트)을 규칙으로 막는다.
'Heavy metals (as Pb)' 는 3단계에서 중금속 총량으로 먼저 잡혀 Pb 로 가지 않는다.
산화물은 서버가 raw_name 의 화학식(K2O 등)을 보고 원소로 환산하므로, 화학식 없이 'oxide'·'氧化'만 있는
이름('Potassium oxide')은 4단계부터 원소로 짐작하지 않고 원문 그대로 낸다.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

AI_CAP = 0.6  # 사전·규칙으로 확정하지 못한 매핑의 신뢰도 상한
NONE = "없음"  # LLM 이 '후보에 없음'으로 답할 때의 값

MATERIAL_KO = {"LI2CO3": "탄산리튬", "LIOH": "수산화리튬"}
ELEMENTS = frozenset("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br
Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os
Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U""".split())

# 모델 테스트(ai/bench/llm)에서 쓴 지시문. 표준 이름만 시드에 맞춰 바꿨다
NORM_SYSTEM = """너는 2차전지 원료 시험성적서(CoA)의 시험 항목명을 사내 표준 항목명으로 맞추는 도우미다.
규칙:
- 후보 목록에서 같은 측정 대상을 뜻하는 이름 하나를 고른다. 확실하지 않거나 후보에 없으면 "없음"을 고른다.
- 총량을 Pb 기준으로 적은 중금속(예: heavy metals as Pb)은 Pb 가 아니라 중금속 총량이다.
- 산화물은 Na2O, K2O, CaO, MgO, Fe2O3 만 각 원소(Na, K, Ca, Mg, Fe)로 본다. 다른 산화물은 "없음".
- 시험 항목이 아닌 것(로트 크기, 분자량, 날짜 등)은 "없음".
JSON 으로만 답한다."""

_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_CJK = r"一-鿿㐀-䶿가-힣"
_PARTICLE_RE = re.compile(r"(?<![a-z0-9])d\s?(10|50|90|99)(?![0-9])")
_CONTENT = re.compile(r"\b(?:content|assay|purity)(?:\s+of)?\b|함량|含量|%", re.IGNORECASE)  # 'Li₂CO₃ 함량' 의 함량
_OXIDE_WORD = re.compile(r"oxide|氧化|산화", re.IGNORECASE)
_ROW_NO = re.compile(r"^\s*\d{1,2}[.)]?\s+(?=\S)")  # 스캔본에서 번호 칸이 항목명에 붙음
_OCR_JUNK = re.compile(r"[{}_^]")
_OCR_I = re.compile(r"(?<=[A-Z])I(?![a-z])")        # 'CI' → 'Cl', 'AI' → 'Al'
_OCR_ZERO = re.compile(r"(?<=[A-Z])0(?=\d)")       # 'S04' → 'SO4'
_OCR_LI = re.compile(r"\bL[I1l|(/]?(?=2\s*C)")      # 'LI2CO3'·'L2CO3'·'L(2CO3' → 'Li2CO3' (원소 기호 L 은 없다)
_OCR_D0 = re.compile(r"(?<=[Dd])([159])[DdOo](?![0-9A-Za-z])")  # 'D1D'·'D5O' → 'D10'·'D50'
_LATIN_WORD = re.compile(r"[a-z]+")
GUESS_CUTOFF = 0.85  # 스캔본 짐작에서 앞 단어 유사도 기준 ('suffate' ~ 'sulfate' 0.857)


@dataclass(frozen=True)
class Mapping:
    name: str
    source: str  # "dictionary" | "ai"
    cap: float   # 이 항목 신뢰도의 상한
    by_llm: bool = field(default=False, compare=False)  # LLM 제안 (pipeline 이 문서 단위로 한 번 더 거른다)


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
    def __init__(self, material_code: str, mappings: dict[str, str] | None = None, llm=None):
        """llm: coa_ai.llm.LLMClient (없으면 6단계를 건너뛴다)."""
        material = (material_code or "").strip().upper()
        self.material = material
        self.llm = llm
        self._candidates: dict[str, str] = {}
        self._other_material_aliases: set[str] = set()
        self.mappings = {k.strip(): v for k, v in (mappings or {}).items()}
        self.mappings_ci = {canon(k): v for k, v in self.mappings.items()}
        self.names: dict[str, str] = {}
        self.aliases: dict[str, str] = {}
        self.formulas: dict[str, str] = {}
        for code, item in load_vocab()["items"].items():
            allowed = item.get("materials")
            if allowed and material not in allowed:
                self._other_material_aliases.update(canon(a) for a in item.get("aliases", []))
                continue
            self.names[code] = item["name"]
            self._candidates.setdefault(item["name"], item.get("meaning", ""))
            for a in item.get("aliases", []):
                self.aliases[canon(a)] = code
                self.aliases.setdefault(_compact(a), code)
            for f in item.get("formulas", []):
                self.formulas[f] = code
        self._fuzzy_keys = [a for a in self.aliases if len(a) >= 6]
        # 원소 항목의 산화물 화학식 (Na2O, K2O …). 서버가 환산하는 것만 사전에 있다
        self._oxides = [f for f, code in self.formulas.items() if self.names[code] in ELEMENTS and f != self.names[code]]

    # ------------------------------------------------------------------
    def map(self, raw_name: str) -> Mapping:
        raw = (raw_name or "").strip()
        if raw in self.mappings:
            return Mapping(self.mappings[raw], "dictionary", 1.0)
        if canon(raw) in self.mappings_ci:
            return Mapping(self.mappings_ci[canon(raw)], "dictionary", 1.0)

        code = self._exact(raw) or self._rules(raw) or self._ocr_retry(raw)
        if code:
            return Mapping(self.names[code], "dictionary", 1.0)
        if self._oxide_without_formula(raw):
            return Mapping(raw, "ai", AI_CAP)

        base = canon(_without_parens(raw))
        close = difflib.get_close_matches(base, self._fuzzy_keys, n=1, cutoff=0.88) if len(base) >= 6 else []
        if close:
            return Mapping(self.names[self.aliases[close[0]]], "ai", AI_CAP)
        guess = self._ocr_guess(raw, base)
        if guess:
            return Mapping(self.names[guess], "ai", AI_CAP)
        if self.llm is not None and not self._element_only(raw) and not self._other_material(raw):
            suggested = self._ask_llm(raw)
            if suggested:
                return Mapping(suggested, "ai", AI_CAP, by_llm=True)
        return Mapping(raw, "ai", AI_CAP)

    def _ocr_retry(self, raw: str) -> str | None:
        """스캔본 잡음을 걷어 낸 이름으로 규칙을 다시 본다. 결과는 사전·규칙에 있는 이름뿐이라 새 항목을 만들지 않는다."""
        cleaned = _OCR_JUNK.sub("", _ROW_NO.sub("", raw, count=1))
        cleaned = _OCR_D0.sub(r"\g<1>0", _OCR_LI.sub("Li", cleaned))
        cleaned = _OCR_ZERO.sub("O", _OCR_I.sub("l", cleaned))
        if not cleaned.strip():
            return None
        if cleaned != raw:
            code = self._exact(cleaned) or self._rules(cleaned) or self._resolve(re.split(r"[(（]", cleaned)[0])
            if code:
                return code
        # 한자·한글 이름 뒤의 잡음('钾κ', '水分1.0', '外观 一'): 앞의 한자·한글 이름만 본다
        m = re.match(rf"\s*([{_CJK}]+)", cleaned)
        return self._alias(m.group(1)) if m else None

    def _ocr_guess(self, raw: str, base: str) -> str | None:
        """확정은 못 하지만 짐작할 수 있는 스캔본 이름 (map 이 ai·신뢰도 상한 0.6 으로 낸다)."""
        if "+" in raw:  # 'Sodium + Potassium (Na+K)' 를 앞 단어만 보고 Na 로 붙이지 않는다
            return None
        words = _LATIN_WORD.findall(base)
        for n in range(min(3, len(words)), 0, -1):
            phrase = " ".join(words[:n])
            if len(phrase) < 5:
                continue
            close = difflib.get_close_matches(phrase, self._fuzzy_keys, n=1, cutoff=GUESS_CUTOFF)
            code = self.aliases.get(phrase) or (self.aliases[close[0]] if close else None)
            if code:
                return code
        # '硼日': 한자 원소명 뒤의 기호 B 를 비슷한 한자로 읽음. 한 글자 원소명일 때만
        m = re.match(rf"\s*([{_CJK}])[{_CJK}](?![{_CJK}])", raw)
        code = self._alias(m.group(1)) if m else None
        return code if code and self.names[code] in ELEMENTS else None

    def candidates(self) -> list[tuple[str, str]]:
        """LLM 에 주는 후보: (표준 항목명, 뜻). 이 원자재에서 쓰는 이름만."""
        return list(self._candidates.items())

    def _other_material(self, raw: str) -> bool:
        return canon(_without_parens(raw)) in self._other_material_aliases or canon(raw) in self._other_material_aliases

    def _oxide_without_formula(self, raw: str) -> bool:
        """'Potassium oxide', '氧化钾': 산화물이라고만 하고 서버가 환산할 화학식(K2O 등)이 이름에 없다."""
        if not _OXIDE_WORD.search(raw):
            return False
        text = strip_charges(unicodedata.normalize("NFKC", raw))
        return not any(re.search(rf"(?<![A-Za-z0-9]){f}(?![a-z0-9])", text) for f in self._oxides)

    def _element_only(self, raw: str) -> bool:
        token = _formula_token(raw)
        return token in ELEMENTS and token not in self.formulas

    def _ask_llm(self, raw: str) -> str | None:
        names = [name for name, _ in self.candidates()]
        lines = "\n".join(f"- {name}: {meaning}" for name, meaning in self.candidates())
        user = f"원자재: {MATERIAL_KO.get(self.material, self.material)}\n후보:\n{lines}\n\n항목명: {raw}"
        schema = {"type": "object", "properties": {"name": {"type": "string", "enum": [*names, NONE]}},
                  "required": ["name"]}
        answer = self.llm.json_chat(NORM_SYSTEM, user, schema, max_tokens=64)
        name = (answer or {}).get("name")
        return name if name in self._candidates else None

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

        # 입도 D10·D50·D90·D99 ('度' 는 粒度 를 粮度·检度 로 잘못 읽은 스캔본도 받으려고)
        m = _PARTICLE_RE.search(c)
        if m and (c.strip() in {"d10", "d50", "d90", "d99"} or any(k in c for k in ("particle", "度", "입도", "psd", "size"))):
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

        # 화학식·이름 + 함량 표기: 'Li₂CO₃ 함량', 'Li2CO3含量', 'K₂O content', 'Content of Li2CO3', 'Li2CO3 (%)'
        core = _CONTENT.sub(" ", _without_parens(raw)).strip(" ,:")
        if core and core != raw.strip():
            code = self._resolve(core)
            if code:
                return code

        # 이름 전체가 화학식: 'Li₂CO₃', 'Na₂O', 'SO₄', 'Cl'
        return self._formula(raw)
