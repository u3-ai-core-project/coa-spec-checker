"""[담당: 고도영] 스캔본 결과의 원본 좌표(bbox)가 맞는 칸을 가리키는지 (개발계획 참고 사항 7번 기록 항목).

정답 좌표는 같은 PDF 를 텍스트 경로로 읽은 bbox 다. 기울기 단계는 이미지를 2° 돌리며 캔버스를 넓혔으므로
(samples.LEVELS, expand=True) 정답 좌표도 같은 변환으로 옮긴다. 항목은 score.py 와 같은 방식(표준명 순서)으로 짝짓는다.

    python bench/bbox.py [엔진=coa_ai]
  적중   : 결과 bbox 중심이 정답 bbox(사방 쪽 폭의 0.5% 여유) 안
  중심 거리: 쪽 폭 대비 %
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from PIL import Image

from coa_ai import extract
from samples import FIXTURES, LEVELS, OUT, REAL_DIR
from score import key

SKEW_DEG = 2.0
MARGIN = 0.005


@lru_cache
def truth_items(doc: str, material: str) -> list[dict]:
    pdf = FIXTURES / f"{doc}.pdf"
    if not pdf.exists():
        pdf = REAL_DIR / f"{doc}.pdf"
    return [i.__dict__ for i in extract(pdf, material_code=material).items]


def _to_level_px(b: dict, level: str, size0: tuple[float, float], size: tuple[int, int]) -> tuple[float, ...]:
    """정답 bbox(원본 쪽 비율) → 그 단계 이미지의 픽셀 사각형 (x0, y0, x1, y1)."""
    w0, h0 = size0
    x0, y0, x1, y1 = b["x"] * w0, b["y"] * h0, (b["x"] + b["w"]) * w0, (b["y"] + b["h"]) * h0
    if level != "skew":
        sx, sy = size[0] / w0, size[1] / h0
        return x0 * sx, y0 * sy, x1 * sx, y1 * sy
    a = math.radians(SKEW_DEG)  # PIL rotate: 반시계, 캔버스를 넓혀 새 중심에 둔다
    cx, cy, ncx, ncy = w0 / 2, h0 / 2, size[0] / 2, size[1] / 2
    pts = [(ncx + (x - cx) * math.cos(a) + (y - cy) * math.sin(a), ncy - (x - cx) * math.sin(a) + (y - cy) * math.cos(a))
           for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def _iou(a, b) -> float:
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def main(engine: str = "coa_ai") -> None:
    stats: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for line in (OUT / "results" / f"{engine}.jsonl").read_text().splitlines():
        r = json.loads(line)
        if not r.get("pred"):
            continue
        size = Image.open(OUT / r["image"]).size
        dpi = LEVELS[r["level"]][0]
        truth = truth_items(r["doc"], r["material"])
        pool = defaultdict(list)
        for t in truth:
            pool[key(t["normalized_name"])].append(t)
        for p in r["pred"]["items"]:
            cands = pool.get(key(p["normalized_name"]))
            if not cands or not p.get("bbox"):
                continue
            t = cands.pop(0)
            if not t["bbox"] or t["bbox"]["page"] != p["bbox"]["page"]:
                continue
            # 원본 쪽 크기(픽셀). 기울기 단계 이미지는 캔버스를 넓혀서 이미지 크기와 다르다
            page_w_in, page_h_in = _page_inches(r["doc"])
            tb = _to_level_px(t["bbox"], r["level"], (page_w_in * dpi, page_h_in * dpi), size)
            pb = p["bbox"]
            ob = (pb["x"] * size[0], pb["y"] * size[1], (pb["x"] + pb["w"]) * size[0], (pb["y"] + pb["h"]) * size[1])
            ocx, ocy = (ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2
            m = MARGIN * size[0]
            s = stats[r["level"]]
            s["hit"].append(tb[0] - m <= ocx <= tb[2] + m and tb[1] - m <= ocy <= tb[3] + m)
            s["dist"].append(100 * math.dist((ocx, ocy), ((tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2)) / size[0])
            s["iou"].append(_iou(ob, tb))
    print("| 단계 | 항목 | 적중 | 중심 거리 중앙값 (쪽 폭 %) | IoU 중앙값 |")
    print("| --- | --- | --- | --- | --- |")
    for level in ["original", "lowres", "skew", "blur", "all"]:
        if level == "all":
            s = {k: [v for lv in stats.values() for v in lv[k]] for k in ("hit", "dist", "iou")}
        else:
            s = stats.get(level)
        if not s or not s["hit"]:
            continue
        n = len(s["hit"])
        print(f"| {level} | {n} | {100 * sum(s['hit']) / n:.1f}% | {statistics.median(s['dist']):.2f} | "
              f"{statistics.median(s['iou']):.2f} |")


@lru_cache
def _page_inches(doc: str) -> tuple[float, float]:
    import pymupdf
    pdf = FIXTURES / f"{doc}.pdf"
    if not pdf.exists():
        pdf = REAL_DIR / f"{doc}.pdf"
    with pymupdf.open(pdf) as d:
        r = d[0].rect
    return r.width / 72, r.height / 72


if __name__ == "__main__":
    main(*sys.argv[1:])
