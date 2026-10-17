"""[담당: 고도영] 모델 테스트 채점 (홍채령 님 채점 스크립트를 받기 전 임시 채점기).

지표 (참고 사항 8번 결과표의 열)
  - 항목 인식률 : 정답 항목 중 같은 표준 항목명(normalized_name)으로 찾은 비율
  - 수치 일치율 : 정답 항목 중 찾았고 결과 값까지 같은 비율 (값을 못 찾은 항목도 분모에 들어간다)
                 값 비교: 숫자 목록과 앞의 부등호(<, ≤, >, ≥)가 같으면 일치. 숫자가 없으면 글자만 비교
  - 머리글 일치율: 정답에 값이 있는 머리글 필드 중 맞힌 비율
                 lot_no·test_date 는 정확히 같아야 하고, supplier·origin·applied_standard 는 한쪽이 다른 쪽을 포함하면 일치

    python bench/score.py            # results/*.jsonl → 표 출력
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from samples import OUT

RESULTS = OUT / "results"
STRICT_FIELDS = ("lot_no", "test_date")
LOOSE_FIELDS = ("supplier", "origin", "applied_standard")

_OPS = {"<": "<", "≤": "≤", "<=": "≤", "=<": "≤", ">": ">", "≥": "≥", ">=": "≥", "=>": "≥"}
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _flat(text: str | None) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[^0-9a-z가-힣一-鿿]+", "", text.casefold())


def key(name: str | None) -> str:
    return _flat(name)


def value_key(value: str | None) -> tuple:
    text = unicodedata.normalize("NFKC", value or "").replace("−", "-").replace(" ", "")
    nums = tuple(float(n.replace(",", ".")) for n in _NUM.findall(text))
    if not nums:
        return ("text", _flat(text))
    m = re.match(r"(<=|=<|>=|=>|[<≤>≥])", text)
    return ("num", _OPS[m.group(1)] if m else "", nums)


def score_items(truth: list[dict], pred: list[dict]) -> tuple[int, int, int]:
    """(정답 항목 수, 찾은 수, 값까지 맞은 수). 같은 표준명이 여러 번이면 순서대로 짝짓는다."""
    pool = defaultdict(list)
    for p in pred:
        pool[key(p.get("normalized_name"))].append(p)
    found = correct = 0
    for t in truth:
        cands = pool.get(key(t["normalized_name"]))
        if not cands:
            continue
        p = cands.pop(0)
        found += 1
        correct += value_key(p.get("raw_value")) == value_key(t["raw_value"])
    return len(truth), found, correct


def score_fields(truth: dict, pred: dict) -> tuple[int, int]:
    total = hit = 0
    for f in STRICT_FIELDS + LOOSE_FIELDS:
        t = truth.get(f)
        if not t:
            continue
        total += 1
        p = _flat(pred.get(f))
        if f in STRICT_FIELDS:
            hit += p == _flat(t)
        else:
            hit += bool(p) and (p in _flat(t) or _flat(t) in p)
    return total, hit


def load(engine_file: Path) -> list[dict]:
    return [json.loads(line) for line in engine_file.read_text().splitlines() if line.strip()]


def summarize(rows: list[dict]) -> dict:
    agg = Counter()
    times = []
    for r in rows:
        truth = json.loads((OUT / "truth" / f"{r['doc']}.json").read_text())
        pred = r.get("pred") or {"items": []}
        n, found, correct = score_items(truth["items"], pred.get("items", []))
        ft, fh = score_fields(truth, pred)
        agg.update(items=n, found=found, correct=correct, fields=ft, fields_hit=fh, samples=1,
                   errors=int(bool(r.get("error"))))
        times.append(r["seconds"])
    pct = lambda a, b: round(100 * agg[a] / agg[b], 1) if agg[b] else None  # noqa: E731
    return {"samples": agg["samples"], "errors": agg["errors"], "item_recall": pct("found", "items"),
            "value_match": pct("correct", "items"), "field_match": pct("fields_hit", "fields"),
            "sec_median": round(statistics.median(times), 1) if times else None}


def main(argv: list[str]) -> None:
    files = [Path(a) for a in argv] or sorted(RESULTS.glob("*.jsonl"))
    print("엔진\t단계\t샘플\t오류\t항목 인식률\t수치 일치율\t머리글 일치율\t중앙값 초/장")
    for f in files:
        rows = load(f)
        levels = ["all"] + sorted({r["level"] for r in rows}, key=["original", "lowres", "skew", "blur"].index)
        for level in levels:
            s = summarize([r for r in rows if level == "all" or r["level"] == level])
            print(f"{f.stem}\t{level}\t{s['samples']}\t{s['errors']}\t{s['item_recall']}\t{s['value_match']}\t"
                  f"{s['field_match']}\t{s['sec_median']}")


if __name__ == "__main__":
    main(sys.argv[1:])
