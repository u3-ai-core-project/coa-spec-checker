"""[담당: 고도영] 가상 CoA 생성기 v2(소성훈 님) 정답 → 평가 스크립트(backend/evaluation, 홍채령 님) 정답 라벨.

    python tools/synth_gt.py data/generated/synth_v2/A_li2co3 --out data/generated/synth_eval/gt

- 열화본 1개 = 정답 JSON 1개. 파일 이름이 PDF 이름과 같아서 평가 스크립트가 추출 결과와 짝짓는다.
- 항목명은 사내 규격 item_name(표준명)으로 바꾼다. 생성기에 새 항목이 생기면 조용히 넘기지 않고 멈춘다.
- 표에 없는 유도 줄(합산·중금속 줄에서 만든 원소, value_type=derived)은 추출 대상이 아니라서 뺀다.
- 사내 규격 없는 참고 항목(REF)은 판정·사유코드 키를 적지 않는다 (평가 스크립트: 키가 없으면 채점 안 함).
- 판정 정답은 생성기 기준 그대로다. 규격 복사·합산 초과의 판정(확인 필요 vs 판정 불가)은 회의 5차 안건 2에서 정한다.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ITEM_NAMES = {
    "appearance": "외관", "li2co3": "순도", "lioh": "LiOH 함량", "co3": "탄산", "so4": "황산염", "cl": "염화물",
    "h2o": "수분", "mag": "자성이물", "heavy_metals": "중금속 총량", "insoluble": "불용분",
    "d10": "입도 D10", "d50": "입도 D50", "d90": "입도 D90", "na_k": "Na+K",
    "na": "Na", "k": "K", "ca": "Ca", "mg": "Mg", "fe": "Fe", "cu": "Cu", "mn": "Mn", "si": "Si",
    "ni": "Ni", "cr": "Cr", "zn": "Zn", "pb": "Pb", "al": "Al", "boron": "B",
}
JUDGEMENT = {"PASS": "pass", "FAIL": "fail", "INDETERMINATE": "undetermined", "CHECK": "check", "MISSING": "missing"}
NO_REASON = {"OK", "BOUND_WITHIN_LIMIT"}
LOT = {"ACCEPT": "approve", "HOLD": "hold", "REJECT": "reject"}
DOC_ISSUES = {"DATE_CONFLICT": "DATE_CONFLICT", "LOT_MISMATCH": "LOT_MISMATCH", "MATERIAL_MISMATCH": "PRODUCT_MISMATCH"}
DATE_FORMATS = {"A": "%d-%b-%Y", "B": "%Y-%m-%d", "D": "%m/%d/%Y"}  # D 는 월/일/년 (생성기 README)
NO_UNIT = {"", "-", "—"}


def convert(gen_dir: str | Path, out_dir: str | Path) -> list[str]:
    """생성기 결과 폴더(ground_truth.json 이 있는 곳) → out_dir/<열화본 이름>.json. 만든 이름 목록을 돌려준다."""
    data = json.loads((Path(gen_dir) / "ground_truth.json").read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    material = data["material_key"].upper()
    stems = []
    for doc in data["documents"]:
        base = {
            "material_code": material, "source": "synthetic", "form": doc["template"], "split": doc["split"],
            "header": _header(doc),
            "items": [i for i in (_item(it) for it in doc["items"]) if i is not None],
            "lot_recommendation": LOT[doc["lot_recommendation"]],
            "document_issues": [DOC_ISSUES[c] for c in doc["reason_codes"] if c in DOC_ISSUES],
        }
        for variant in doc["variants"]:
            path = Path(variant)
            label = {"document_id": path.stem, **base, "degradation": path.parent.name}
            (out / f"{path.stem}.json").write_text(json.dumps(label, ensure_ascii=False, indent=1), encoding="utf-8")
            stems.append(path.stem)
    return stems


def _header(doc: dict) -> dict:
    f = doc["fields"]
    header = {"supplier": doc["supplier"], "lot_no": f.get("lot_no")}
    if f.get("test_date"):
        header["test_date"] = datetime.strptime(f["test_date"], DATE_FORMATS[doc["template"]]).strftime("%Y-%m-%d")
    return header


def _item(it: dict) -> dict | None:
    if it["value_type"] == "derived":
        return None
    if it["item_id"] not in ITEM_NAMES:
        raise ValueError(f"표준명을 모르는 생성기 항목: {it['item_id']} ({it.get('printed_name')}) — ITEM_NAMES 에 추가하세요")
    item = {"normalized_name": ITEM_NAMES[it["item_id"]]}
    if it["value_type"] != "missing":
        item["raw_value"] = it["result"]
        item["unit"] = None if it["unit"] in NO_UNIT else it["unit"]
        if it.get("value_std") is not None:
            item["converted_value"] = it["value_std"]
    if it["expected"] in JUDGEMENT:
        item["judgement"] = JUDGEMENT[it["expected"]]
        item["reason_code"] = _reason(it)
    return item


def _reason(it: dict) -> str | None:
    if it["reason"] in NO_REASON or it["expected"] == "PASS":
        return None
    if it["reason"] == "ND_WITH_LOD":  # 검출한계가 사내 상한보다 큰 ND (서버 이름)
        return "LOD_ABOVE_LIMIT"
    return it["reason"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python tools/synth_gt.py", description="생성기 v2 정답 → 평가 스크립트 정답 라벨")
    ap.add_argument("gen_dirs", nargs="+", type=Path, help="생성기 결과 폴더 (ground_truth.json 이 있는 곳)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    n = sum(len(convert(d, args.out)) for d in args.gen_dirs)
    print(f"정답 라벨 {n}개 → {args.out}")


if __name__ == "__main__":
    main()
