"""[담당: 고도영] 머리글 필드: 로트, 시험일, 원산지, 협력사, 적용 규격 (+ v1.4 대비 제품명·발행일·유효기한).

라벨(영·중·한)을 찾은 뒤 값을 짝짓는다.
  - 'LOT NO. : L0049ZH1' 처럼 같은 칸 안에 콜론 뒤 값
  - 'Lot Number   A0266047' 처럼 같은 줄 오른쪽 칸
  - '批  号 / Batch No.' 처럼 두 줄짜리 라벨의 오른쪽에 있는 값 (가상 B)
라벨이 없으면 쓰지 않는다. 특히 시험일이 없을 때 제조일로 대신하지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from coa_ai.dates import find_dates, parse_date
from coa_ai.models import Page, Phrase
from coa_ai.pdf_text import phrases

# 필드별 라벨. 앞의 것이 우선이다.
LABELS: dict[str, list[str]] = {
    "lot_no": [r"lot\s*(?:number|no\.?|#|nr\.?)", r"batch\s*/\s*lot", r"lot\s*/\s*batch",
               r"manufacturer'?s\s+batch\s*(?:no\.?|number)", r"batch\s*(?:number|no\.?)", r"批\s*号",
               r"로트\s*(?:번호|no\.?)?", r"제조\s*번호",
               # 접미사 없는 'Lot:', 'Batch:' 는 맨 마지막에 본다 (크기·수량 라벨은 제외)
               r"lot(?!\s*size)", r"batch(?!\s*(?:size|quantity|qty|weight|disposition))"],
    "test_date": [r"quality\s*test\s*/\s*release\s*date", r"(?:test|analysis)\s*date", r"date\s+of\s+(?:test|analysis)",
                  r"sampled\s*/\s*tested", r"检\s*验\s*日\s*期", r"检\s*测\s*日\s*期", r"시험\s*일(?:자)?"],
    "issue_date": [r"date\s+of\s+issue", r"issue\s*date", r"issued(?:\s+on)?", r"报\s*告\s*日\s*期",
                   r"签\s*发\s*日\s*期", r"발행\s*일(?:자)?"],
    "expiry_date": [r"expiry\s*date", r"expiration\s*date", r"exp\.?\s*date", r"保\s*质\s*期", r"有\s*效\s*期",
                    r"유효\s*기간", r"사용\s*기한"],
    "origin": [r"country\s+of\s+origin", r"origin", r"原\s*产\s*地", r"원\s*산\s*지"],
    "product_name": [r"product\s*name", r"产\s*品\s*名\s*称", r"제\s*품\s*명", r"품\s*명", r"description", r"product"],
    "supplier": [r"supplier", r"manufacturer", r"vendor", r"供\s*应\s*商", r"生\s*产\s*厂\s*家", r"제조사", r"공급사"],
    "standard": [r"applied\s+standard", r"standard", r"检\s*验\s*依\s*据", r"执\s*行\s*标\s*准", r"conforms\s+to",
                 r"적용\s*규격", r"시험\s*기준"],
    "grade": [r"grade", r"等\s*级", r"등급"],
    "customer": [r"customer(?:\s*po)?", r"客\s*户(?:\s*名\s*称)?", r"고객", r"ship\s*to", r"sold\s*to", r"consignee"],
}
_COMPILED = {f: [re.compile(rf"^(?:{p})(?=$|[\s:：])", re.IGNORECASE) for p in pats] for f, pats in LABELS.items()}

_INLINE_FIELDS = {"lot_no", "test_date", "issue_date", "expiry_date"}  # 값 검사가 있어 콜론 없이 붙어도 된다
_INLINE_LABEL = re.compile(r"^conforms\s+to\s", re.IGNORECASE)  # 'Conforms to CVL-SPEC-…'
_LOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/.]{2,}$")
# 제품 규격 계열만 (ISO 9001 같은 품질 시스템, ASTM 시험법 번호는 적용 규격이 아님)
_STANDARD_RE = re.compile(r"\b(?:GB/T|YS/T|HG/T)\s*\d+(?:\.\d+)?-\d{4}(?:\s*\(?(?:Grade\s*)?D\d\)?)?", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"(?:co\.?,?\s*ltd\.?|company\s+limited|pty\.?\s*ltd\.?|\bltd\.?|\blimited\b|\binc\.?|"
                        r"\bcorp(?:oration)?\.?|\bgmbh\b|\bs\.a\.|\bb\.?v\.?\b|\bn\.v\.|\bllc\b|\bplc\b|"
                        r"有限公司|株式会社|\(주\)|주식회사)", re.IGNORECASE)
KNOWN_SUPPLIERS = [
    (re.compile(r"acros\s+organics", re.I), "Acros Organics"),
    (re.compile(r"alfa\s*aesar|www\.alfa\.com", re.I), "Alfa Aesar"),
    (re.compile(r"daejung|대정화금", re.I), "대정화금 (DAEJUNG CHEMICALS)"),
    (re.compile(r"piochem", re.I), "Piochem"),
    (re.compile(r"nanotrun|trunnano", re.I), "Nanotrun"),
    (re.compile(r"thermo\s*fisher", re.I), "Thermo Fisher Scientific"),
    (re.compile(r"sigma[-\s]?aldrich", re.I), "Sigma-Aldrich"),
]


@dataclass(frozen=True)
class _Label:
    field: str
    rank: int          # LABELS 안의 순서 (작을수록 우선)
    phrase: Phrase
    inline: str | None  # 같은 칸 안의 값 (콜론 뒤, 또는 라벨 바로 뒤)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).replace("’", "'").strip()


def _find_label(ph: Phrase) -> _Label | None:
    text = _norm(ph.text)
    for field, pats in _COMPILED.items():
        for rank, pat in enumerate(pats):
            m = pat.match(text)
            if not m:
                continue
            rest = text[m.end():].strip()
            # 중·영 병기 라벨('检验依据 Standard：…', '报告日期 Date of Issue：…')은 뒤쪽 라벨까지 넘긴다
            again = next((m2 for p2 in pats if (m2 := p2.match(rest))), None)
            if again:
                rest = rest[again.end():].strip()
            colon = rest[:1] in ":："
            if colon:
                rest = rest[1:].strip()
            if rest and not colon and field not in _INLINE_FIELDS and not _INLINE_LABEL.match(text):
                continue  # 'Product Code …' 처럼 다른 라벨의 앞부분만 같은 경우
            return _Label(field, rank, ph, rest or None)
    return None


def _candidates(label: _Label, all_phrases: list[Phrase], labels: dict[Phrase, _Label]) -> list[str]:
    """라벨 오른쪽 칸들을 가까운 순서로. 같은 줄을 먼저 보고, 없으면 위아래 한 줄 높이 안을 본다."""
    lb = label.phrase.box
    cands = []
    for ph in all_phrases:
        if ph is label.phrase or ph in labels or ph.box.x0 < lb.x1 - 1:
            continue
        dy = abs(ph.box.cy - lb.cy)
        if dy > 1.2 * max(lb.height, ph.box.height):
            continue
        cands.append((ph.line != label.phrase.line, round(dy / 3), ph.box.x0 - lb.x1, _norm(ph.text)))
    return [c[3] for c in sorted(cands, key=lambda c: c[:3])]


def _valid(field: str, value: str | None) -> str | None:
    if not value:
        return None
    if field == "lot_no":
        token = value.split()[0]
        return token if _LOT_RE.match(token) and re.search(r"\d", token) else None
    if field in ("test_date", "issue_date", "expiry_date"):
        dates = find_dates(value)
        if not dates:
            return None
        return dates[-1] if field == "test_date" else dates[0]  # 'Sampled / Tested a / b' 는 뒤 날짜가 시험일
    return value


def extract_fields(pages: list[Page]) -> dict[str, str | None]:
    """첫 페이지(없으면 다음 페이지)에서 머리글 필드를 읽는다."""
    out: dict[str, str | None] = {k: None for k in
                                  ("supplier", "lot_no", "test_date", "origin", "applied_standard",
                                   "product_name", "issue_date", "expiry_date")}
    page = next((p for p in pages if p.lines), None)
    if page is None:
        return out
    all_phrases = [ph for i, ln in enumerate(page.lines) for ph in phrases(ln, i)]
    labels = {ph: lab for ph in all_phrases if (lab := _find_label(ph))}

    found: dict[str, tuple[int, str]] = {}
    customer_values: set[str] = set()
    for lab in sorted(labels.values(), key=lambda lb: (lb.rank, lb.phrase.box.y0)):
        options = ([lab.inline] if lab.inline else []) + _candidates(lab, all_phrases, labels)
        if lab.field == "customer":
            customer_values.update(options[:1])
            continue
        # 라벨 바로 뒤 글이나 가장 가까운 칸이 값 형식에 맞지 않으면 다음 후보를 본다 ('Lot Size' 는 로트가 아님)
        value = next((v for o in options if (v := _valid(lab.field, o))), None)
        if value and lab.field not in found:
            found[lab.field] = (lab.rank, value)

    for key in ("lot_no", "test_date", "issue_date", "expiry_date", "origin", "product_name"):
        if key in found:
            out[key] = found[key][1]
    out["supplier"] = found.get("supplier", (0, None))[1] or _supplier(page, all_phrases, customer_values)
    out["applied_standard"] = _standard(found, page, all_phrases)
    return out


def _supplier(page: Page, all_phrases: list[Phrase], customer_values: set[str]) -> str | None:
    text = " ".join(ln.text for ln in page.lines)
    for pat, name in KNOWN_SUPPLIERS:
        if pat.search(text):
            return name
    top = [ph for ph in all_phrases if ph.box.y1 <= page.height * 0.25 and _norm(ph.text) not in customer_values]
    hits = [ph for ph in top if _SUFFIX_RE.search(ph.text) and len(ph.text) <= 80]
    if not hits:
        return None
    latin = [ph for ph in hits if re.search(r"[A-Za-z]{3}", ph.text)]
    return _norm((latin or hits)[0].text)


def _standard(found: dict[str, tuple[int, str]], page: Page, all_phrases: list[Phrase]) -> str | None:
    if "standard" in found:
        return found["standard"][1]
    m = _STANDARD_RE.search(" ".join(ln.text for ln in page.lines[: max(1, len(page.lines) // 2)]))
    if m:
        return m.group(0).strip()
    if "grade" in found:
        return found["grade"][1]
    m = re.search(r"\bACS\s+reagent\b", " ".join(ln.text for ln in page.lines), re.IGNORECASE)
    return m.group(0) if m else None
