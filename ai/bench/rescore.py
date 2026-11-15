"""[담당: 고도영] 저장해 둔 모델 원출력(raw_text)으로 예측을 다시 만든다 (변환 코드를 고친 뒤 모델을 다시 돌리지 않고).

    python bench/rescore.py surya paddleocr-vl
원출력이 잘려 저장된 샘플(20000자)은 건드리지 않고 개수만 알린다.
"""
from __future__ import annotations

import json
import sys

from PIL import Image

from engines import _rules, blocks_to_page
from samples import OUT


def main(engines: list[str]) -> None:
    for engine in engines:
        path = OUT / "results" / f"{engine}.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        redone = skipped = 0
        for r in rows:
            raw = (r.get("pred") or {}).get("raw_text")
            if not raw or len(raw) >= 20000:
                skipped += 1
                continue
            if engine == "surya":
                blocks = [(tuple(b), c) for b, c in json.loads(raw)]
            else:
                w, h = Image.open(OUT / r["image"]).size
                blocks = [((0, 0, w, h), raw)]
            pred = _rules(blocks_to_page(blocks, r["dpi"]), r["material"])
            pred["raw_text"] = raw
            r["pred"] = pred
            redone += 1
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{engine}: {redone} rescored, {skipped} skipped")


if __name__ == "__main__":
    main(sys.argv[1:])
