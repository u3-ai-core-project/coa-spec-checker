"""[담당: 고도영] 명령줄 실행.

    python -m coa_ai COA_A_0007.pdf --material LIOH          # 추출 결과 JSON
    python -m coa_ai data/raw/real/*.pdf --material LI2CO3   # 여러 파일 점검표
    python -m coa_ai COA_D_0007.pdf --material LIOH --llm-url http://127.0.0.1:8090   # LLM 단계 포함
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from coa_ai.llm import LLMClient
from coa_ai.pipeline import ExtractionFailed, extract

LOW_CONFIDENCE = 0.8  # 서버 LOW_CONFIDENCE_THRESHOLD 와 같은 값


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m coa_ai", description="CoA PDF 추출")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--material", required=True, help="원자재 구분 (예: LI2CO3, LIOH)")
    parser.add_argument("--summary", action="store_true", help="파일이 1개여도 점검표로 출력")
    parser.add_argument("--llm-url", default=os.environ.get("LLM_BASE_URL"),
                        help="LLM 서버 주소 (기본: 환경변수 LLM_BASE_URL, 없으면 LLM 없이)")
    args = parser.parse_args(argv)
    llm = LLMClient(args.llm_url) if args.llm_url else None

    if len(args.files) == 1 and not args.summary:
        try:
            result = extract(args.files[0], material_code=args.material, llm=llm)
        except ExtractionFailed as e:
            print(f"추출 실패: {e}", file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("파일\t문서 유형\t항목\t사전 매핑\t낮은 신뢰도\t로트\t시험일\t실패 사유")
    for path in args.files:
        try:
            r = extract(path, material_code=args.material, llm=llm)
        except ExtractionFailed as e:
            print(f"{path.name}\t-\t0\t0\t0\t-\t-\t{e}")
            continue
        mapped = sum(i.mapping_source == "dictionary" for i in r.items)
        low = sum(i.confidence < LOW_CONFIDENCE for i in r.items)
        print(f"{path.name}\t{r.doc_type}\t{len(r.items)}\t{mapped}\t{low}\t{r.lot_no or '-'}\t{r.test_date or '-'}\t")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
