"""[담당: 고도영] 문서별 채점표: 어느 문서·단계에서 항목을 놓쳤는지 본다.

    python bench/report.py rapidocr [--level original]
"""
from __future__ import annotations

import argparse
import json

from score import OUT, RESULTS, load, score_fields, score_items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("engine")
    ap.add_argument("--level", default=None)
    args = ap.parse_args()
    print("문서\t단계\t항목(찾음/전체)\t값 일치\t머리글\t초")
    for r in load(RESULTS / f"{args.engine}.jsonl"):
        if args.level and r["level"] != args.level:
            continue
        t = json.loads((OUT / "truth" / f"{r['doc']}.json").read_text())
        p = r.get("pred") or {"items": []}
        n, f, c = score_items(t["items"], p.get("items", []))
        ft, fh = score_fields(t, p)
        print(f"{r['doc']}\t{r['level']}\t{f}/{n}\t{c}/{n}\t{fh}/{ft}\t{r['seconds']}{'  ERROR' if r.get('error') else ''}")


if __name__ == "__main__":
    main()
