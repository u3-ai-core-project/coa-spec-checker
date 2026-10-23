"""[담당: 고도영] 모델 테스트 실행: manifest 의 이미지를 엔진에 넣고 결과·시간·최대 메모리를 JSONL 로 쓴다.

    python bench/run.py rapidocr
    python bench/run.py qwen3.5-2b --levels original --docs COA_A_0007,COA_B_0005
    python bench/run.py qwen3.5-2b --base-url http://127.0.0.1:8090 --tag docker-cpu   # Docker 로 띄운 서버

이미 기록한 샘플은 건너뛰므로 중간에 멈춰도 다시 실행하면 이어서 돈다.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import traceback

import psutil

import engines as eng
from engines import VLMS

OCR_ENGINES = ["coa_ai", "rapidocr", "paddleocr", "easyocr", "tesseract", "surya"]
from samples import OUT


class PeakRss:
    """프로세스(와 자식)의 최대 RSS(MB)를 0.2초마다 잰다."""

    def __init__(self, pid: int):
        self.proc = psutil.Process(pid)
        self.peak = 0.0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                rss = self.proc.memory_info().rss + sum(c.memory_info().rss for c in self.proc.children(recursive=True))
                self.peak = max(self.peak, rss / 2**20)
            except psutil.Error:
                pass
            time.sleep(0.2)

    def stop(self) -> float:
        self._stop.set()
        self._t.join()
        return round(self.peak)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=[*OCR_ENGINES, *VLMS])
    ap.add_argument("--levels", default="original,lowres,skew,blur")
    ap.add_argument("--docs", default="", help="쉼표로 구분한 문서 이름 앞부분 (비우면 전부)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-schema", action="store_true", help="JSON 스키마 제약 없이 생성")
    ap.add_argument("--shrink", type=float, default=0.1, help="OCR 검출 상자 축소 비율 (OCR 엔진 전용)")
    ap.add_argument("--use-cls", action="store_true", help="OCR 글줄 방향 분류 켜기 (OCR 엔진 전용)")
    ap.add_argument("--model", default="small", choices=["small", "medium"], help="RapidOCR PP-OCRv6 모델 크기")
    ap.add_argument("--paddle-params", action="store_true", help="RapidOCR 검출 설정을 PaddleOCR 원본과 같게")
    args = ap.parse_args()
    # kill(TERM)·셸 종료로 끊겨도 finally 에서 llama-server 를 끈다 (남으면 다음 실행이 그 서버에 붙는다)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_, s=sig: sys.exit(128 + s))

    manifest = json.loads((OUT / "manifest.json").read_text())
    levels = args.levels.split(",")
    prefixes = [d for d in args.docs.split(",") if d]
    todo = [m for m in manifest if m["level"] in levels and (not prefixes or any(m["doc"].startswith(p) for p in prefixes))]

    out_dir = OUT / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.engine}{'__' + args.tag if args.tag else ''}.jsonl"
    done = set()
    if out_file.exists():
        done = {json.loads(line)["id"] for line in out_file.read_text().splitlines() if line.strip()}
    todo = [m for m in todo if m["id"] not in done]
    print(f"{args.engine}: {len(todo)} samples to run -> {out_file}", flush=True)
    if not todo:
        return

    pid = os.getpid()
    if args.engine == "coa_ai":
        engine = eng.ProductEngine()
    elif args.engine == "rapidocr":
        engine = eng.RapidOcrEngine(shrink=args.shrink, use_cls=args.use_cls, model=args.model,
                                     paddle_params=args.paddle_params)
    elif args.engine == "paddleocr":
        engine = eng.PaddleOcrEngine(shrink=args.shrink)
    elif args.engine == "easyocr":
        engine = eng.EasyOcrEngine()
    elif args.engine == "tesseract":
        engine = eng.TesseractEngine()
    elif args.engine == "surya":
        engine = eng.SuryaEngine(base_url=args.base_url)
    elif args.engine == "paddleocr-vl":
        engine = eng.PaddleOcrVlEngine(base_url=args.base_url)
        pid = engine.pid
    else:
        engine = eng.LlamaServerEngine(args.engine, base_url=args.base_url, use_schema=not args.no_schema)
        pid = engine.pid
    meter = PeakRss(pid) if pid else None
    try:
        with out_file.open("a") as fh:
            for n, m in enumerate(todo, 1):
                t0 = time.perf_counter()
                pred, err = None, None
                try:
                    pred = engine.run(OUT / m["image"], m["material"], m["dpi"])
                except Exception:  # noqa: BLE001 — 실패도 결과로 기록한다
                    err = traceback.format_exc(limit=3)
                sec = round(time.perf_counter() - t0, 2)
                fh.write(json.dumps({**m, "engine": args.engine, "seconds": sec, "pred": pred, "error": err,
                                     "peak_rss_mb": meter.peak if meter else None}, ensure_ascii=False) + "\n")
                fh.flush()
                items = len(pred["items"]) if pred else "ERR"
                print(f"[{n}/{len(todo)}] {m['id']}  {sec}s  items={items}", flush=True)
    finally:
        if meter:
            print(f"peak RSS {meter.stop()} MB", flush=True)
        if hasattr(engine, "close"):
            engine.close()


if __name__ == "__main__":
    main()
