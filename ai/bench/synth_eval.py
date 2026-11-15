"""[담당: 고도영] 가상 CoA 생성기 v2 문서를 coa_ai 로 읽어 평가 스크립트(backend/evaluation) 입력을 만든다.

    python bench/synth_eval.py data/generated/synth_v2/{A,B,D}_li2co3 --out data/generated/synth_eval
    python bench/synth_eval.py data/generated/synth_v2/A_li2co3 --out out --levels original --llm-url http://127.0.0.1:8090
    cd ../backend && python -m evaluation.run --gt ../ai/data/generated/synth_eval/gt --pred ../ai/data/generated/synth_eval/pred

- out/gt   : 정답 라벨 (tools/synth_gt.py)
- out/pred : 추출 결과 (ExtractionInput 형식. 판정이 없으므로 평가 스크립트는 추출 지표만 계산한다)
- 추출 실패는 출력 파일을 만들지 않는다 → 평가 스크립트가 '0개 인식'으로 센다. 사유는 out/failures.csv.
- 문서별 시간은 out/timings.csv. 이미 있는 출력은 건너뛰므로 끊겨도 다시 실행하면 이어서 돈다 (--force 로 다시).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from coa_ai import ExtractionFailed, LLMClient, extract  # noqa: E402
from tools.synth_gt import convert  # noqa: E402


def run(gen_dirs: list[Path], out: Path, *, levels: set[str] | None = None, llm_url: str | None = None,
        force: bool = False) -> None:
    llm = LLMClient(llm_url) if llm_url else None
    (out / "pred").mkdir(parents=True, exist_ok=True)
    jobs = []
    for gen in gen_dirs:
        material = json.loads((gen / "ground_truth.json").read_text(encoding="utf-8"))["material_key"].upper()
        convert(gen, out / "gt")
        for pdf in sorted((gen / "pdf").rglob("*.pdf")):
            if levels is None or pdf.parent.name in levels:
                jobs.append((pdf, material))
    timings, failures = _read(out / "timings.csv"), _read(out / "failures.csv")
    for n, (pdf, material) in enumerate(jobs, 1):
        dest = out / "pred" / f"{pdf.stem}.json"
        if (dest.exists() or pdf.stem in failures) and not force:
            continue
        t0 = time.perf_counter()
        try:
            r = extract(pdf, material_code=material, llm=llm)
        except ExtractionFailed as e:
            failures[pdf.stem] = {"doc": pdf.stem, "level": pdf.parent.name, "reason": str(e)}
            dest.unlink(missing_ok=True)
        else:
            dest.write_text(json.dumps(r.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
            failures.pop(pdf.stem, None)
        timings[pdf.stem] = {"doc": pdf.stem, "level": pdf.parent.name, "seconds": f"{time.perf_counter() - t0:.2f}"}
        print(f"[{n}/{len(jobs)}] {pdf.stem} {timings[pdf.stem]['seconds']}s", flush=True)
        _write(out / "timings.csv", timings, ["doc", "level", "seconds"])
        _write(out / "failures.csv", failures, ["doc", "level", "reason"])


def _read(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["doc"]: r for r in csv.DictReader(f)}


def _write(path: Path, rows: dict[str, dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows[k] for k in sorted(rows))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python bench/synth_eval.py", description="생성기 v2 문서 → 평가 스크립트 입력")
    ap.add_argument("gen_dirs", nargs="+", type=Path, help="생성기 결과 폴더 (ground_truth.json 이 있는 곳)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--levels", help="열화 단계만 골라 실행 (예: original,blur)")
    ap.add_argument("--llm-url", help="LLM 서버 주소 (없으면 규칙만)")
    ap.add_argument("--force", action="store_true", help="이미 있는 출력도 다시 만들기")
    args = ap.parse_args(argv)
    run(args.gen_dirs, args.out, levels=set(args.levels.split(",")) if args.levels else None,
        llm_url=args.llm_url, force=args.force)


if __name__ == "__main__":
    main()
