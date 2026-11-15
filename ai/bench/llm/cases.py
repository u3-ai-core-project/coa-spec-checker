"""[담당: 고도영] LLM 후보 테스트 문제 (기획안 v2 ★3 결과 의미 분류, ★4 항목 정규화, ★8 문의 초안).

실물 CoA 에서 뽑은 문제는 정답 파일(ai/data/generated/bench/truth, gitignore)에서 실행할 때 만든다.
규칙만으로 어려운 변형은 아래에 직접 적었다 (처음 보는 항목명, 규격 복사의 다른 표기, 여러 언어의 '검출 안 됨').
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data" / "generated" / "bench"
VOCAB = json.loads((ROOT / "coa_ai" / "vocab.json").read_text())["items"]
NONE = "없음"

# 표준 항목명 설명 (LLM 에 주는 후보 목록). 동의어 사전을 그대로 주지 않고 뜻만 준다. 제품과 같은 vocab.json 의 meaning
MEANING = {it["name"]: it.get("meaning", "") for it in VOCAB.values()}
# 2026-10-18 표준 이름을 규격 시드에 맞춰 바꿨다. 그 전에 만든 정답 파일·결과 파일의 옛 이름을 새 이름으로 읽는다
RENAMED = {"Cl": "염화물", "중금속": "중금속 총량"}


def standard_names(material: str) -> list[str]:
    out = []
    for it in VOCAB.values():
        if it.get("materials") and material not in it["materials"]:
            continue
        if it["name"] not in out:
            out.append(it["name"])
    return out


# ---------------------------------------------------------------------------
# ★4 항목 정규화
# ---------------------------------------------------------------------------
# (원자재, 원문 항목명, 정답). 사전에 없는 표기를 일부러 골랐다
NORM_SYNTHETIC = [
    ("LI2CO3", "Natrium", "Na"), ("LI2CO3", "Sodium, Na (ICP-OES)", "Na"), ("LI2CO3", "钠含量", "Na"),
    ("LI2CO3", "나트륨(Na)", "Na"), ("LI2CO3", "Kalium", "K"), ("LI2CO3", "Potassium content", "K"),
    ("LI2CO3", "Calcium, as Ca", "Ca"), ("LI2CO3", "Magnesium content (Mg)", "Mg"), ("LI2CO3", "Ferrum", "Fe"),
    ("LI2CO3", "Iron as Fe2O3", "Fe"), ("LI2CO3", "Lead (Pb), single element", "Pb"),
    ("LI2CO3", "Heavy Metals as Pb", "중금속 총량"), ("LI2CO3", "Heavy metal (Pb basis)", "중금속 총량"),
    ("LI2CO3", "重金属(以Pb计)", "중금속 총량"), ("LI2CO3", "Chlorides (as Cl-)", "염화물"), ("LI2CO3", "氯含量", "염화물"),
    ("LI2CO3", "Sulphate content", "황산염"), ("LI2CO3", "SO4 2-", "황산염"), ("LI2CO3", "Moisture (H2O)", "수분"),
    ("LI2CO3", "Water by Karl Fischer", "수분"), ("LI2CO3", "Insolubles in water", "불용분"),
    ("LI2CO3", "HCl-insoluble matter", "불용분"), ("LI2CO3", "Magnetic substance", "자성이물"),
    ("LI2CO3", "Magnetic foreign matter (Fe+Cr+Ni+Zn)", "자성이물"), ("LI2CO3", "D50 particle size", "입도 D50"),
    ("LI2CO3", "粒度 D90", "입도 D90"), ("LI2CO3", "Li2CO3 assay (dry basis)", "순도"),
    ("LI2CO3", "Purity of lithium carbonate", "순도"), ("LI2CO3", "Physical appearance", "외관"),
    ("LIOH", "LiOH content (as LiOH)", "LiOH 함량"), ("LIOH", "Carbonate content as CO3", "탄산"),
    ("LIOH", "碳酸锂含量", NONE),  # 수산화리튬 문서의 탄산리튬 함량은 LiOH 함량이 아니다
    ("LIOH", "Nitrate (NO3-)", "질산염"),
    # 항목이 아니거나 표준 목록에 없는 것
    ("LI2CO3", "Lot Size", NONE), ("LI2CO3", "Molecular weight", NONE), ("LI2CO3", "Bulk density", NONE),
    ("LI2CO3", "Total impurities", NONE), ("LI2CO3", "Silver (Ag)", NONE), ("LI2CO3", "Arsenic", NONE),
    ("LI2CO3", "Specific surface area (BET)", NONE), ("LI2CO3", "Expiry date", NONE), ("LI2CO3", "Retest date", NONE),
    # 2026-10-25 규격 세트(PR #20)에 강열감량이 생기고 서버가 K2O·MgO 를 환산(PR #14)해 정답이 '없음'에서 바뀜.
    # bench/README.md 의 10-18 결과표는 바꾸기 전 정답으로 잰 것
    ("LI2CO3", "MgO", "Mg"), ("LI2CO3", "Loss on ignition", "강열감량"),
]


def norm_cases() -> list[dict]:
    """실물 CoA 항목명(정답 = 텍스트 경로 매핑, 표준 목록 밖이면 '없음') + 변형."""
    manifest = {m["doc"]: m["material"] for m in json.loads((BENCH / "manifest.json").read_text())}
    seen, out = set(), []
    for f in sorted((BENCH / "truth").glob("*.json")):
        material = manifest.get(f.stem)
        if material is None:
            continue
        names = standard_names(material)
        for it in json.loads(f.read_text())["items"]:
            key = (material, it["raw_name"])
            if key in seen:
                continue
            seen.add(key)
            name = RENAMED.get(it["normalized_name"], it["normalized_name"])
            label = name if name in names else NONE
            out.append({"set": "real", "material": material, "raw_name": it["raw_name"], "truth": label})
    for material, raw, label in NORM_SYNTHETIC:
        out.append({"set": "synthetic", "material": material, "raw_name": raw, "truth": label})
    return out


# ---------------------------------------------------------------------------
# ★3 결과 의미 분류
# ---------------------------------------------------------------------------
VALUE_KINDS = ["number", "bound", "nd", "spec_copy", "pass_text", "description"]
KIND_KO = {"number": "숫자 결과", "bound": "부등호 결과(<, ≤, 이하)", "nd": "검출 안 됨",
           "spec_copy": "규격 문구를 결과 칸에 복사", "pass_text": "합격·적합 문구", "description": "서술(색·형태 등)"}

# (항목명, 결과 칸, 규격 칸, 정답). 규칙(정확 일치·정규식)이 놓치기 쉬운 표기
VALUE_SYNTHETIC = [
    ("Sodium (Na)", "≤100 ppm", "100 ppm max", "spec_copy"),
    ("Iron (Fe)", "Max 20 ppm", "≤ 20 ppm", "spec_copy"),
    ("Sulfate (SO4)", "0.35 % max", "≤ 0.35 %", "spec_copy"),
    ("Calcium (Ca)", "NMT 20 ppm", "≤20 ppm", "spec_copy"),
    ("철(Fe)", "20 ppm 이하", "≤ 20 ppm", "spec_copy"),
    ("钠Na", "≤0.0020", "不大于0.0020", "spec_copy"),
    ("Potassium (K)", "=<0.002 %", "=<0.2 %", "bound"),
    ("Lead (Pb)", "< 10 ppm", "≤ 20 ppm", "bound"),
    ("Copper (Cu)", "Less than 1 ppm", "≤ 5 ppm", "bound"),
    ("나트륨(Na)", "10 ppm 미만", "20 ppm 이하", "bound"),
    ("Magnesium (Mg)", "BDL", "≤ 10 ppm", "nd"),
    ("Nickel (Ni)", "< LOD", "≤ 5 ppm", "nd"),
    ("铁Fe", "未检出", "≤0.0010", "nd"),
    ("Zinc (Zn)", "ND (<0.5 ppm)", "≤ 5 ppm", "nd"),
    ("Chromium (Cr)", "Below detection limit", "≤ 5 ppm", "nd"),
    ("Appearance", "Conforms to specification", "White powder", "pass_text"),
    ("Heavy metals (as Pb)", "Meets ACS specifications", "≤ 5 ppm", "pass_text"),
    ("Appearance", "As per specification", "White crystalline powder", "pass_text"),
    ("外观", "合格", "白色粉末", "pass_text"),
    ("외관", "적합", "백색 분말", "pass_text"),
    ("Appearance", "White, free-flowing powder", "White powder", "description"),
    ("外观 Appearance", "白色结晶粉末", "白色结晶粉末，无可见杂质", "description"),
    ("Assay", "99.62 % (dry basis)", "≥ 99.5 %", "number"),
    ("Particle size D50", "8.5 µm", "3 – 20 µm", "number"),
]

_PASS = re.compile(r"conform|complies|compliant|pass|meets|符合|合格|적합|합격|이상\s*없음", re.I)
_DIGIT = re.compile(r"\d")
_BOUND = re.compile(r"^\s*(<|>|≤|≥|=<|>=|<=|=>|max\b|min\b)|max\.?\s*$|이하|미만|不大于|不小于", re.I)
_ND = re.compile(r"(?<![a-z])n\.?\s?d\.?(?![a-z])|none\s+detected|not\s+detected|검출\s*안\s*됨|검출되지\s*않|불검출|미검출",
                 re.I)


def _same(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"\s+", "", s.replace("≤", "<=").replace("=<", "<=").replace("≥", ">=")).casefold()
    return norm(a) == norm(b)


def _label_real(value: str, spec: str | None) -> str:
    """실물 결과 칸의 정답. 사람이 확인한 규칙으로 붙이고, 애매한 것은 value_cases 에서 뺀다."""
    if spec and _same(value, spec):
        # 'White'|'White', '90 ppm'|'90 ppm' 처럼 조건(부등호·이하)이 없는 같은 글은 복사인지 정상 보고인지 애매해 뺀다
        return "spec_copy" if _BOUND.search(value) else "?"
    if _ND.search(value):
        return "nd"
    if _PASS.search(value):
        return "pass_text"
    if not _DIGIT.search(value):
        return "description"
    if _BOUND.search(value):
        return "bound"
    if re.match(r"^\s*[-+]?\d", value):
        return "number"
    return "?"


# 제품 규칙 표(coa_ai.meaning)를 만든 뒤, 결과를 보기 전에 따로 적은 변형 (규칙을 만들 때 보지 않은 표기).
# 위 VALUE_SYNTHETIC 은 규칙 표를 만들 때 본 문제라 제품 경로의 일반화 평가에는 이것을 쓴다
VALUE_HOLDOUT = [
    ("Sodium (Na)", "5 ppm Max.", "≤ 5 ppm", "spec_copy"),
    ("Iron (Fe)", "not more than 0.05%", "≤ 0.05 %", "spec_copy"),
    ("Calcium (Ca)", "≦ 20 ppm", "Max 20 ppm", "spec_copy"),
    ("Chloride", "0.01 % 以下", "≤ 0.01 %", "spec_copy"),
    ("Iron (Fe)", "Max. 0.001%", "0.001 % max", "spec_copy"),
    ("Potassium (K)", "< 0.5 mg/kg", "≤ 10 mg/kg", "bound"),
    ("Lead (Pb)", "Below 1 ppm", "≤ 5 ppm", "bound"),
    ("Copper (Cu)", "<0.5", "≤ 5", "bound"),
    ("Heavy metals (as Pb)", "Less than 10 ppm", "≤ 10 ppm", "bound"),
    ("Magnesium (Mg)", "n.d.", "≤ 10 ppm", "nd"),
    ("Nickel (Ni)", "Not detected (LOD 0.1 ppm)", "≤ 5 ppm", "nd"),
    ("Zinc (Zn)", "未检出(<0.1)", "≤0.0005", "nd"),
    ("Chromium (Cr)", "Absent", "≤ 5 ppm", "nd"),
    ("Arsenic", "Nil", "≤ 1 ppm", "nd"),
    ("Appearance", "Complies", "White powder", "pass_text"),
    ("Identification", "Passes test", "Positive", "pass_text"),
    ("Appearance", "Within specification", "White crystalline powder", "pass_text"),
    ("外观", "符合规定", "白色粉末", "pass_text"),
    ("Solubility", "Satisfactory", "Clear solution", "pass_text"),
    ("Appearance", "OK", "White powder", "pass_text"),
    ("Identification", "Meets requirement", "IR conforms", "pass_text"),
    ("Appearance", "Clear, colorless solution", "Clear solution", "description"),
    ("Color", "Off-white", "White", "description"),
    ("외관", "흰색 결정성 분말", "백색 분말", "description"),
    ("Assay", "99.71%", "≥ 99.5 %", "number"),
    ("Moisture (H2O)", "0.12 % (KF)", "≤ 0.5 %", "number"),
    ("Sulfate (SO4)", "0.008 %w/w", "≤ 0.05 %w/w", "number"),
    ("Particle size D50", "D50 = 6.2 µm", "3 – 20 µm", "number"),
    ("Sodium (Na)", "12 ppm (ICP-OES)", "≤ 50 ppm", "number"),
]


def holdout_cases() -> list[dict]:
    return [{"set": "holdout", "raw_name": n, "raw_value": v, "raw_spec": s, "truth": t} for n, v, s, t in VALUE_HOLDOUT]


def value_cases() -> list[dict]:
    seen, out = set(), []
    for f in sorted((BENCH / "truth").glob("*.json")):
        for it in json.loads(f.read_text())["items"]:
            if not it["raw_value"]:
                continue
            key = (it["raw_name"], it["raw_value"], it["raw_spec"])
            if key in seen:
                continue
            seen.add(key)
            label = _label_real(it["raw_value"], it["raw_spec"])
            if label != "?":
                out.append({"set": "real", "raw_name": it["raw_name"], "raw_value": it["raw_value"],
                            "raw_spec": it["raw_spec"], "truth": label})
    for name, value, spec, label in VALUE_SYNTHETIC:
        out.append({"set": "synthetic", "raw_name": name, "raw_value": value, "raw_spec": spec, "truth": label})
    return out


# ---------------------------------------------------------------------------
# ★8 문의 초안 (PR #5 inquiry_draft.LotRequest / FollowUpLine 형식)
# ---------------------------------------------------------------------------
# 백엔드 inquiry_draft.SUPPLIER_REQUEST 를 옮긴 것 (제품 경로는 백엔드 AIDrafter 가 이 문구를 request 로 넘긴다)
SUPPLIER_REQUEST = {
    "OUT_OF_SPEC": "단위·표기 오류 여부와 재시험 가능 여부 확인",
    "CONVERTED_OOS": "산화물 기준 결과의 원소 기준 값 또는 단위·표기 확인",
    "SPEC_COPIED": "실측값이 기재된 CoA 재발행",
    "MISSING_REQUIRED": "해당 항목의 시험 결과(별도 성적서) 송부",
}


def inquiry_lots(case: dict) -> list[dict]:
    """DRAFT_CASES 1건 → coa_ai.inquiry 입력 (백엔드 AIDrafter.to_inquiry_lots 와 같은 변환)."""
    return [{"lot_no": lot["lot_no"], "material_name": lot["material_name"], "requests": [
        {"target": ln["target"], "label": ln["label"], "why": ln["why"],
         "request": SUPPLIER_REQUEST.get(ln["code"], ln["condition"]), "raw_value": ln["raw_value"]}
        for ln in lot["lines"]]} for lot in case["lots"]]


def _line(target, code, label, why, condition, raw_value):
    return {"target": target, "code": code, "label": label, "why": why, "condition": condition,
            "raw_value": raw_value, "to_supplier": True}


DRAFT_CASES = [
    {"id": "nd_no_lod", "supplier": "Thermo Fisher Scientific", "lots": [
        {"lot_no": "A0475173", "material_name": "탄산리튬", "lines": [
            _line("Fe", "ND_NO_LOD", "검출 안 됨, 검출한계 미기재", "검출 안 됨으로 적혔지만 검출한계가 없어 사내 상한 5 ppm 충족 여부를 알 수 없음",
                  "검출한계 ≤ 5 ppm (또는 정량값)", "N.D.")]}]},
    {"id": "spec_copied", "supplier": "Acros Organics", "lots": [
        {"lot_no": "A0468916", "material_name": "탄산리튬", "lines": [
            _line("Na", "SPEC_COPIED", "결과 칸에 규격 문구 기재", "결과 칸에 규격 문구(=<1000 ppm)가 그대로 적힘",
                  "실측값이 적힌 CoA (결과 칸에 규격 문구가 적힘)", "=<1000 ppm"),
            _line("K", "SPEC_COPIED", "결과 칸에 규격 문구 기재", "결과 칸에 규격 문구(=<100 ppm)가 그대로 적힘",
                  "실측값이 적힌 CoA (결과 칸에 규격 문구가 적힘)", "=<100 ppm")]}]},
    {"id": "missing_and_lod", "supplier": "Ruilan Lithium (Yichun) Co., Ltd.", "lots": [
        {"lot_no": "LH26022103", "material_name": "수산화리튬", "lines": [
            _line("자성이물", "MISSING_REQUIRED", "필수 항목 누락", "사내 필수 항목인 자성이물이 CoA 에 없음",
                  "별도 성적서 값 또는 자체 시험값 입력", None),
            _line("Pb", "LOD_ABOVE_LIMIT", "검출한계가 사내 상한보다 큼", "보고값 < 10 ppm 의 검출한계가 사내 상한 5 ppm 보다 큼",
                  "검출한계 ≤ 5 ppm (또는 정량값)", "< 10 ppm")]}]},
    {"id": "two_lots", "supplier": "Acros Organics", "lots": [
        {"lot_no": "A0468916", "material_name": "탄산리튬", "lines": [
            _line("Ca", "SPEC_COPIED", "결과 칸에 규격 문구 기재", "결과 칸에 규격 문구(=<100 ppm)가 그대로 적힘",
                  "실측값이 적힌 CoA (결과 칸에 규격 문구가 적힘)", "=<100 ppm")]},
        {"lot_no": "A0474013", "material_name": "탄산리튬", "lines": [
            _line("황산염", "BOUND_ABOVE_LIMIT", "보고 상한이 사내 상한보다 큼", "보고값 < 0.2 % 가 사내 상한 0.05 % 보다 커서 충족 여부를 알 수 없음",
                  "정량값 또는 상한값 ≤ 0.05 % 보고", "< 0.2 %")]}]},
    {"id": "out_of_spec", "supplier": "Selmora Lithium S.A.", "lots": [
        {"lot_no": "SL25-0008", "material_name": "수산화리튬", "lines": [
            _line("탄산", "OUT_OF_SPEC", "규격 초과", "0.36 % 로 사내 상한 0.35 % 를 0.01 %p 초과",
                  "단위·표기 오류가 아님을 확인 (확인되면 부적합 확정)", "0.36 %")]}]},
    {"id": "ambiguous_pb", "supplier": "Alfa Aesar", "lots": [
        {"lot_no": "B19Z009", "material_name": "탄산리튬", "lines": [
            _line("Pb", "AMBIGUOUS_ANALYTE", "측정 대상 모호(총량만 기재)", "Pb 단일값 없이 Heavy metals (as Pb) < 10 ppm 만 있어 사내 Pb 상한 5 ppm 판정 불가",
                  "Pb 단일 분석값 ≤ 5 ppm", "Heavy metals (as Pb) < 10 ppm")]}]},
]


# ---------------------------------------------------------------------------
# ★3 역할 분담안: 규칙이 못 읽는 칸 원문만 LLM 이 정규형(종류·부등호·숫자·단위)으로 바꾸고, 비교는 코드가 한다
# ---------------------------------------------------------------------------
def canon_cases() -> list[dict]:
    import baseline_rules as b
    strings = set()
    for c in value_cases():
        for s in (c["raw_value"], c["raw_spec"]):
            if s and not b.parse(s):
                strings.add(s)
    return [{"id": s, "text": s} for s in sorted(strings)]
