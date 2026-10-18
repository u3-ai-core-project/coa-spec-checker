"""[담당: 고도영] 「개발계획」 참고 사항 8번 결과표 (마크다운).

모든 엔진을 같은 샘플로 비교한다: 기본은 모든 엔진이 끝낸 샘플의 교집합.
처리 시간·최대 메모리는 Docker CPU 측정값(<엔진>__docker-cpu.jsonl, <엔진>.mem)을 쓴다.

    python bench/table.py                 # 공통 샘플 기준
    python bench/table.py --level original
"""
from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from score import RESULTS, load, summarize

ENGINES = [  # (결과 파일 이름, 표에 쓰는 이름)
    ("coa_ai", "coa_ai.extract (제품 경로, RapidOCR small)"),
    ("rapidocr", "RapidOCR (PP-OCR ONNX)"),
    ("rapidocr__default", "RapidOCR 기본 설정"),
    ("rapidocr__medium", "RapidOCR + PP-OCRv6 medium"),
    ("rapidocr__medium-pdet", "RapidOCR + PP-OCRv6 medium + PaddleOCR 검출 설정"),
    ("paddleocr", "PaddleOCR"),
    ("easyocr", "EasyOCR"),
    ("tesseract", "Tesseract"),
    ("surya", "Surya 2"),
    ("glm-ocr", "GLM-OCR"),
    ("qwen3.5-2b", "Qwen3.5-2B"),
    ("lfm2.5-vl-450m", "LFM2.5-VL-450M"),
    ("gemma4-e2b", "Gemma 4 E2B"),
    ("paddleocr-vl", "PaddleOCR-VL-1.6"),
]


def docker_cell(engine: str) -> tuple[str, str, str]:
    """(처리 시간/장, 최대 메모리, Docker 실행 확인)."""
    base, _, variant = engine.partition("__")
    f = RESULTS / f"{base}__docker-cpu.jsonl"
    mem_file = RESULTS / f"{base}.mem"
    if variant and (RESULTS / f"{base}__{variant}-docker-cpu.jsonl").exists():  # 예: rapidocr__medium
        f, mem_file = RESULTS / f"{base}__{variant}-docker-cpu.jsonl", RESULTS / f"{base}-{variant}.mem"
    elif variant and variant != "default":  # 설정이 다르면 기본 엔진 값을 빌려 쓰지 않는다
        return "-", "-", "미측정"
    if not f.exists():
        return "-", "-", "미측정"
    rows = [r for r in load(f) if not r.get("error")]
    if not rows:
        return "-", "-", "실패"
    sec = statistics.median(r["seconds"] for r in rows)
    mem = mem_file.read_text().strip() if mem_file.exists() else ""
    return f"{sec:.0f}초 ({len(rows)}장)", f"{int(mem) / 1024:.1f}GB" if mem else "-", "O"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default=None)
    args = ap.parse_args()
    data = {e: load(RESULTS / f"{e}.jsonl") for e, _ in ENGINES if (RESULTS / f"{e}.jsonl").exists()}
    common = set.intersection(*({r["id"] for r in rows} for rows in data.values()))
    if args.level:
        common = {i for i in common if i.endswith("__" + args.level)}
    print(f"공통 샘플 {len(common)}장\n")
    print("| 후보 | 항목 인식률 | 수치 일치율 | 머리글 일치율 | 처리 시간/장 (Docker CPU) | 최대 메모리 | Docker 실행 확인 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for e, label in ENGINES:
        if e not in data:
            continue
        s = summarize([r for r in data[e] if r["id"] in common])
        sec, mem, ok = docker_cell(e)
        print(f"| {label} | {s['item_recall']}% | {s['value_match']}% | {s['field_match']}% | {sec} | {mem} | {ok} |")


if __name__ == "__main__":
    main()
