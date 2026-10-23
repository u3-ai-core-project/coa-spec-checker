"""[담당: 고도영] LLM 후보 채점표.

    python bench/llm/score.py            # 마크다운 표
    python bench/llm/score.py --drafts   # 문의 초안 원문도 출력

정규화
  정확도        : 정답(표준 항목명 또는 '없음')과 같은 비율
  잘못된 매핑   : 다른 표준 항목명을 고른 수 (정답이 '없음'인데 고른 것 포함). 제품에서는 '확인 필요'로 가지만 담당자를 헷갈리게 한다
  사전→LLM      : 사전·규칙이 못 찾은 것만 LLM 에 묻는 제품 구조의 결과
결과 의미 분류
  정확도, 규격 복사 재현율·정밀도
문의 초안 (자동 검사, 문장 품질은 사람이 본다)
  지어낸 숫자   : 입력에 없는 숫자를 쓴 초안 수 (근거 인용 정확도 100% 목표)
  항목·조건 누락: 요청 항목명이나 해결 조건의 수치를 빠뜨린 초안 수
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import baseline_rules  # noqa: E402
import cases  # noqa: E402
from run import MODELS, OUT  # noqa: E402

PRODUCT_LABELS = [("product-rules", "제품 경로, 규칙만 (LLM 없음)"), ("product", "제품 경로, 규칙 + Gemma")]

ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr
Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au
Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U""".split())

_NUMBER = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9])")
_LIST_MARK = re.compile(r"^\s*\d+[.)]\s", re.M)


def numbers(text: str) -> set[float]:
    text = _LIST_MARK.sub(" ", re.sub(r"2\s*차\s*전지", " ", text))
    return {float(n) for n in _NUMBER.findall(text)}


def load(name: str) -> dict[str, list[dict]]:
    f = OUT / f"{name}.jsonl"
    rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()] if f.exists() else []
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        if r["task"] == "norm":  # 표준 이름 변경 전 결과도 새 이름으로 읽는다
            r["case"]["truth"] = cases.RENAMED.get(r["case"]["truth"], r["case"]["truth"])
            if r["pred"] and "name" in r["pred"]:
                r["pred"]["name"] = cases.RENAMED.get(r["pred"]["name"], r["pred"]["name"])
        by_task.setdefault(r["task"], []).append(r)
    return by_task


def norm_scores(rows: list[dict], base: dict[str, str] | None = None, element_filter: bool = False) -> dict:
    out = {}
    for subset in ("all", "real", "synthetic"):
        rs = [r for r in rows if subset == "all" or r["case"]["set"] == subset]
        if not rs:
            continue
        preds = [_norm_pred(r, base, element_filter) for r in rs]
        truth = [r["case"]["truth"] for r in rs]
        ok = sum(p == t for p, t in zip(preds, truth))
        wrong = sum(p != t and p != cases.NONE for p, t in zip(preds, truth))
        out[subset] = (round(100 * ok / len(rs), 1), wrong, len(rs))
    return out


def _norm_pred(r: dict, base: dict[str, str] | None, element_filter: bool = False) -> str:
    if base is not None and base.get(r["id"], cases.NONE) != cases.NONE:
        return base[r["id"]]  # 사전·규칙이 찾은 것은 LLM 에 묻지 않는다
    if element_filter and r["case"]["raw_name"].strip() in ELEMENTS:
        return cases.NONE  # 표준 목록에 없는 원소 기호 하나뿐이면 규칙으로 '없음' (사전에 있는 원소는 위에서 이미 찾음)
    return (r["pred"] or {}).get("name", cases.NONE)


def value_scores(rows: list[dict]) -> dict:
    out = {}
    for subset in ("all", "real", "synthetic"):
        rs = [r for r in rows if subset == "all" or r["case"]["set"] == subset]
        if not rs:
            continue
        pred = [(r["pred"] or {}).get("kind") for r in rs]
        truth = [r["case"]["truth"] for r in rs]
        ok = sum(p == t for p, t in zip(pred, truth))
        tp = sum(p == t == "spec_copy" for p, t in zip(pred, truth))
        fn = sum(t == "spec_copy" and p != t for p, t in zip(pred, truth))
        fp = sum(p == "spec_copy" and t != p for p, t in zip(pred, truth))
        out[subset] = {"acc": round(100 * ok / len(rs), 1), "n": len(rs),
                       "copy_recall": f"{tp}/{tp + fn}", "copy_fp": fp}
    return out


def _read(text: str, canon: dict[str, dict]):
    """규칙으로 읽고, 못 읽으면 LLM 정규형. LLM 숫자가 원문에 없으면 버린다 (규칙 검증)."""
    got = baseline_rules.parse(text)
    if got:
        return got
    p = canon.get(text)
    if not p:
        return None
    if p["kind"] in ("value", "range"):
        num = p["number"].strip()
        if not num or num not in text:
            return None
        try:
            return (p["kind"], p["op"] or "=", float(num), p["unit"].lower() or None)
        except ValueError:
            return None
    return (p["kind"], None, None, None)


def hybrid_kind(c: dict, canon: dict[str, dict]) -> str:
    v, spec = c["raw_value"], c["raw_spec"]
    if spec and baseline_rules._spec_key(v) == baseline_rules._spec_key(spec):
        return "spec_copy"
    pv = _read(v, canon)
    if pv is None or pv[0] == "range":
        return "unknown"
    if pv[0] != "value":
        return pv[0]
    _, op, num, unit = pv
    ps = _read(spec, canon) if spec else None
    if ps and ps[0] == "value" and op != "=" and ps[1] == op and ps[2] == num and (not unit or not ps[3] or unit == ps[3]):
        return "spec_copy"  # 같은 부등호·같은 숫자 = 규격 조건을 다시 적음 (코드가 비교)
    return "number" if op == "=" else "bound"


def draft_checks(r: dict) -> dict:
    c = r["case"]
    if r["error"] or not r["pred"]:
        return {"ok": False, "error": r["error"] or "빈 결과"}
    text = r["pred"]["subject"] + "\n" + r["pred"]["body"]
    allowed = numbers(json.dumps({"supplier": c["supplier"], "lots": c["lots"]}, ensure_ascii=False))
    invented = sorted(numbers(text) - allowed)
    missing = []
    for lot in c["lots"]:
        if lot["lot_no"] not in text:
            missing.append(lot["lot_no"])
        for line in lot["lines"]:
            t = line["target"]
            if not re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![a-z])", text):
                missing.append(t)
            for n in numbers(line["condition"]) - numbers(text):
                missing.append(f"{t} 조건 {n:g}")
    return {"ok": True, "invented": invented, "missing": missing, "table": "|" in text,
            "hangul": round(len(re.findall(r"[가-힣]", text)) / max(1, len(re.sub(r"\s", "", text))), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    suffix = f"__{args.tag}" if args.tag else ""
    base_rows = load("baseline")
    base_norm = {r["id"]: r["pred"]["name"] for r in base_rows.get("norm", [])}

    print("### 항목 정규화 (정확도 % / 잘못된 매핑 수)\n")
    print("| 후보 | 전체 | 실물 | 변형(처음 보는 표기) | 사전→LLM 전체 | 사전→LLM 변형 | 초/건 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    b = norm_scores(base_rows.get("norm", []))
    if b:
        cell = lambda s: f"{s[0]} / {s[1]}"
        print(f"| 규칙 베이스라인(사전·규칙·유사도) | {cell(b['all'])} | {cell(b['real'])} | {cell(b['synthetic'])} | - | - | - |")
    for m in MODELS:
        rows = load(m + suffix).get("norm", [])
        if not rows:
            continue
        s, c = norm_scores(rows), norm_scores(rows, base_norm)
        sec = statistics.median(r["seconds"] for r in rows if r["seconds"])
        cell = lambda x: f"{x[0]} / {x[1]}" if x else "-"
        print(f"| {m} | {cell(s.get('all'))} | {cell(s.get('real'))} | {cell(s.get('synthetic'))} | "
              f"{cell(c.get('all'))} | {cell(c.get('synthetic'))} | {sec:.1f} |")

    print("\n### 항목 정규화 역할 분담안: 사전·규칙 → 목록 밖 원소 기호는 규칙으로 '없음' → 나머지만 LLM\n")
    print("| 후보 | 전체 | 실물 | 변형(처음 보는 표기) |")
    print("| --- | --- | --- | --- |")
    for m in MODELS:
        rows = load(m + suffix).get("norm", [])
        if rows:
            f = norm_scores(rows, base_norm, element_filter=True)
            print(f"| 사전·규칙 → {m} | " + " | ".join(f"{f[k][0]} / {f[k][1]}" for k in ("all", "real", "synthetic")) + " |")
    for name, label in PRODUCT_LABELS:
        rows = load(name).get("norm", [])
        if rows:
            f = norm_scores(rows)
            print(f"| {label} | " + " | ".join(f"{f[k][0]} / {f[k][1]}" for k in ("all", "real", "synthetic")) + " |")

    print("\n### 결과 의미 분류 (정확도 % / 규격 복사 찾음 / 규격 복사 오탐)\n")
    print("| 후보 | 전체 | 실물 | 변형 | 초/건 |")
    print("| --- | --- | --- | --- | --- |")
    for name in ["baseline", *MODELS]:
        rows = load(name if name == "baseline" else name + suffix).get("value", [])
        if not rows:
            continue
        s = value_scores(rows)
        cell = lambda x: f"{x['acc']} / {x['copy_recall']} / {x['copy_fp']}" if x else "-"
        s = {k: s.get(k) for k in ("all", "real", "synthetic")}
        secs = [r["seconds"] for r in rows if r["seconds"]]
        label = "규칙 베이스라인(서버 규칙)" if name == "baseline" else name
        print(f"| {label} | {cell(s['all'])} | {cell(s['real'])} | {cell(s['synthetic'])} | "
              f"{statistics.median(secs):.1f} |" if secs else f"| {label} | {cell(s['all'])} | {cell(s['real'])} | {cell(s['synthetic'])} | - |")

    print("\n### 결과 의미 분류 역할 분담안: 규칙이 못 읽는 칸만 LLM 정규형 → 비교는 코드 (정확도 / 복사 찾음 / 복사 오탐)\n")
    print("| 후보 | 전체 | 실물 | 변형 | LLM 에 물은 칸 | 숫자 검증 탈락 |")
    print("| --- | --- | --- | --- | --- | --- |")
    vcases = [r for r in base_rows.get("value", [])]
    for m in MODELS:
        crow = load(m + suffix).get("canon", [])
        if not crow:
            continue
        canon = {r["case"]["text"]: r["pred"] for r in crow if r["pred"]}
        rejected = sum(1 for t in canon if canon[t]["kind"] in ("value", "range") and _read(t, canon) is None)
        fake = [{**r, "pred": {"kind": hybrid_kind(r["case"], canon)}} for r in vcases]
        s = value_scores(fake)
        cell = lambda x: f"{x['acc']} / {x['copy_recall']} / {x['copy_fp']}"
        print(f"| 규칙 + {m} | {cell(s['all'])} | {cell(s['real'])} | {cell(s['synthetic'])} | {len(crow)} | {rejected} |")
    for name, label in PRODUCT_LABELS:
        rows = load(name).get("value", [])
        if rows:
            s = value_scores(rows)
            asked = sum(1 for r in rows if (r["pred"] or {}).get("reason", "").startswith("AI 판단"))
            print(f"| {label} | {cell(s['all'])} | {cell(s['real'])} | {cell(s['synthetic'])} | AI 판단 {asked} | - |")

    print("\n### 결과 의미 분류, 규칙을 만들 때 보지 않은 변형 (정확도 / 복사 찾음 / 복사 오탐)\n")
    print("| 경로 | 정확도 | 틀린 문제 |")
    print("| --- | --- | --- |")
    for name, label in [("baseline", "서버 규칙(글자 일치)"), *PRODUCT_LABELS]:
        rows = load(name).get("holdout", [])
        if rows:
            s = value_scores(rows)["all"]
            wrong = [f"{r['case']['raw_value']}→{(r['pred'] or {}).get('kind')}" for r in rows
                     if (r["pred"] or {}).get("kind") != r["case"]["truth"]]
            print(f"| {label} | {s['acc']} / {s['copy_recall']} / {s['copy_fp']} | {', '.join(wrong)} |")

    print("\n### 문의 초안 (6건, 자동 검사)\n")
    print("| 후보 | 형식 오류 | 지어낸 숫자가 있는 초안 | 항목·조건 누락이 있는 초안 | 표 사용 | 초/건 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for m in MODELS:
        rows = load(m + suffix).get("draft", [])
        if not rows:
            continue
        checks = [draft_checks(r) for r in rows]
        bad = sum(not c["ok"] for c in checks)
        inv = [(r["case"]["id"], c["invented"]) for r, c in zip(rows, checks) if c["ok"] and c["invented"]]
        miss = [(r["case"]["id"], c["missing"]) for r, c in zip(rows, checks) if c["ok"] and c["missing"]]
        tables = sum(c["ok"] and c["table"] for c in checks)
        sec = statistics.median(r["seconds"] for r in rows if r["seconds"])
        print(f"| {m} | {bad} | {len(inv)} {inv if inv else ''} | {len(miss)} {miss if miss else ''} | {tables} | {sec:.1f} |")
        if args.drafts:
            for r in rows:
                print(f"\n---- {m} / {r['case']['id']}\n{r['raw']}\n")
    rows = load("product").get("draft", [])
    if rows:
        fallback = [(r["case"]["id"], r["pred"]["fallback"]) for r in rows if r["pred"] and "fallback" in r["pred"]]
        ok = [r for r in rows if r["pred"] and "subject" in r["pred"]]
        checks = [draft_checks(r) for r in ok]
        inv = sum(1 for c in checks if c["invented"])
        miss = sum(1 for c in checks if c["missing"])
        sec = statistics.median(r["seconds"] for r in rows if r["seconds"])
        print(f"| 제품 경로 (Gemma + 코드 검사) | 템플릿 대체 {len(fallback)} {fallback if fallback else ''} | {inv} | {miss} | "
              f"{sum(c['table'] for c in checks)} | {sec:.1f} |")
        if args.drafts:
            for r in ok:
                print(f"\n---- product / {r['case']['id']}\n제목: {r['pred']['subject']}\n\n{r['pred']['body']}\n")


if __name__ == "__main__":
    main()
