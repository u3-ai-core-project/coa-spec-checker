"""[담당: 고도영] AI 추출 결과(pred)에 서버 판정 엔진을 돌려 판정까지 들어간 출력(pred_judged)을 만든다.

    cd backend
    PYTHONPATH=. .venv/bin/python ../ai/eval/judge_synth.py <pred 폴더> <저장 폴더> LI2CO3-GENV2-EVAL

규격은 backend/seeds/data/spec_items_li2co3.csv 에서 규격 세트 코드로 고른다. 서버·DB 없이 파일만 읽는다.
"""
import csv
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from app.core.enums import SpecType  # noqa: E402
from app.schemas.extraction import ExtractionInput  # noqa: E402
from app.services.judgement.document_checks import check_document  # noqa: E402
from app.services.judgement.engine import judge_document  # noqa: E402
from app.services.judgement.spec_rule import SpecRule  # noqa: E402


def _num(v: str) -> float | None:
    return float(v) if v.strip() else None


def main() -> None:
    src, dst, code = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    dst.mkdir(parents=True, exist_ok=True)
    rows = csv.DictReader(open("seeds/data/spec_items_li2co3.csv", encoding="utf-8-sig"))
    specs = [SpecRule(r["item_name"], r["unit"] or None, _num(r["lsl"]), _num(r["usl"]),
                      SpecType(r["spec_type"].strip()), r["is_required"].strip().lower() == "true")
             for r in rows if r["spec_set_code"] == code]
    for f in sorted(src.glob("*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        raw = raw.get("data", raw) if "success" in raw else raw
        ext = ExtractionInput.model_validate(raw)
        res = judge_document(ext, document_id=f.stem, specs=specs, issues=check_document(ext))
        (dst / f.name).write_text(res.model_dump_json(), encoding="utf-8")
    print(len(list(dst.glob("*.json"))), "건 판정,", code, len(specs), "개 규격")


if __name__ == "__main__":
    main()
