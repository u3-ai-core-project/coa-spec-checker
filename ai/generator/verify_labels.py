#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생성 결과 검증 (정답 라벨 ↔ PDF ↔ 입고 정보 ↔ 분할)
====================================================
사용법:  python verify_labels.py output_A_li2co3 [output_B_li2co3 ...]

검사하는 것
  1. 원본 PDF 글자에 정답 라벨의 결과 문자열이 그대로 있는지, 누락 항목 이름이 정말 없는지  (pdftotext 필요, 없으면 건너뜀)
  2. 정답 판정 다시 계산: 결과 문자열 -> 숫자 -> 표준 단위(산화물이면 원소로 환산) -> 사내 규격 비교가 expected 와 같은지
  3. 로트 권고 규칙 (FAIL > 판정 불가·확인 필요·누락·문서 사유 > 적합) 이 정답과 같은지
  4. 입고 정보: 불일치 사유코드가 있는 문서만 로트·원자재가 다르고 나머지는 같은지
  5. 분할: 같은 원본에서 나온 열화본이 모두 같은 분할(dev/eval) 폴더에 있는지
"""

import csv
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


def pdf_text(path):
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
    return re.sub(r"\s+", " ", out.stdout)


def check(folder):
    folder = Path(folder)
    gt = json.load(open(folder / "ground_truth.json", encoding="utf-8"))
    spec = {s["id"]: s for s in gt["spec_db"]}
    to_std = {(u["doc_unit"], u["std_unit"]): u["factor"] for u in gt["unit_to_std"]}
    ox = {k: v["factor"] for k, v in gt["oxide_to_element"].items()}
    has_pdftotext = bool(shutil.which("pdftotext"))
    err = []
    n_items = 0
    for d in gt["documents"]:
        did = d["doc_id"]
        text = pdf_text(folder / d["file"]) if has_pdftotext else None
        for r in d["items"]:
            n_items += 1
            vt, exp, iid = r["value_type"], r["expected"], r["item_id"]
            if text is not None and r["row"] is not None:
                res = r["result"]
                if res and res not in text and res.replace(" ", "") not in text.replace(" ", ""):
                    err.append(f"{did} {iid}: 결과 '{res}' 가 PDF 에 없음")
            if vt == "missing" and text is not None and iid != "mag":     # 자성이물은 비고·Notes 에도 이름이 나옴
                name = spec[iid]["name"].split(" (")[0]
                if gt["template"] != "B" and re.search(rf"\b{re.escape(name)}\b", text):
                    err.append(f"{did} {iid}: 누락이라는데 PDF 에 '{name}' 이 있음")
            if iid not in spec or vt in ("missing", "derived", "combined", "ambiguous", "spec_like", "text"):
                continue
            s = spec[iid]
            lsl, usl = s.get("lsl"), s.get("usl")
            if vt == "exact":
                v = float(NUM.findall(r["result"])[0]) * to_std[(r["unit"], s["unit"])]
                if r.get("basis"):
                    v *= ox[iid]
                ok = (lsl is None or v >= lsl - 1e-9) and (usl is None or v <= usl + 1e-9)
                want = "PASS" if ok else "FAIL"
            else:                                   # bound / nd
                nums = NUM.findall(r["result"])
                if not nums:                        # LOD 없는 ND
                    want = "CHECK"
                else:
                    b = float(nums[-1]) * to_std[(r["unit"], s["unit"])]
                    want = "PASS" if usl is not None and b <= usl + 1e-9 else "INDETERMINATE"
            if want != exp:
                err.append(f"{did} {iid}: 결과 '{r['result']}' 로 다시 판정하면 {want}, 정답은 {exp}")
        exps = [r["expected"] for r in d["items"]]
        rec = ("REJECT" if "FAIL" in exps else
               "HOLD" if any(e in ("INDETERMINATE", "CHECK", "MISSING") for e in exps)
               or set(d["reason_codes"]) & {"DATE_CONFLICT", "LOT_MISMATCH", "MATERIAL_MISMATCH"} else "ACCEPT")
        if rec != d["lot_recommendation"]:
            err.append(f"{did}: 로트 권고 다시 계산 {rec} ≠ 정답 {d['lot_recommendation']}")
        if d["is_normal"] and d["lot_recommendation"] != "ACCEPT":
            err.append(f"{did}: 정상 문서인데 로트 권고가 {d['lot_recommendation']}")

    # 입고 정보
    rc = {r["receipt_id"]: r for r in csv.DictReader(open(folder / "receipts.csv", encoding="utf-8-sig"))}
    for d in gt["documents"]:
        r = rc[d["receipt_id"]]
        lot_bad = r["received_lot"] != d["fields"]["lot_no"]
        mat_bad = r["material"] != gt["material"]
        if lot_bad != ("LOT_MISMATCH" in d["injected_codes"]):
            err.append(f"{d['doc_id']}: 입고 로트 불일치 여부가 사유코드와 다름")
        if mat_bad != ("MATERIAL_MISMATCH" in d["injected_codes"]):
            err.append(f"{d['doc_id']}: 입고 원자재 불일치 여부가 사유코드와 다름")

    # 분할
    split_of = {}
    n_pdf = 0
    for v in csv.DictReader(open(folder / "variants.csv", encoding="utf-8-sig")):
        n_pdf += 1
        split_of.setdefault(v["doc_id"], set()).add(v["split"])
        if f"/{v['split']}/" not in v["file"]:
            err.append(f"{v['file']}: 폴더와 분할 표시가 다름")
        if not (folder / v["file"]).exists():
            err.append(f"{v['file']}: 파일 없음")
    leak = [k for k, s in split_of.items() if len(s) > 1]
    if leak:
        err.append(f"원본 하나의 열화본이 dev/eval 에 섞임: {leak[:5]}")

    docs = gt["documents"]
    print(f"[{folder.name}] 문서 {len(docs)}장, 항목 줄 {n_items}개, 열화본 포함 PDF {n_pdf}개"
          f"{'' if has_pdftotext else ' (pdftotext 없음: PDF 글자 대조 건너뜀)'}")
    print("   로트 권고:", dict(Counter(d["lot_recommendation"] for d in docs)),
          " 정상 비율:", f"{sum(d['is_normal'] for d in docs) / len(docs) * 100:.0f}%",
          " 분할:", dict(Counter(d["split"] for d in docs)))
    print("   사유코드:", dict(Counter(c for d in docs for c in d["injected_codes"]).most_common()))
    for e in err[:30]:
        print("   X", e)
    print(f"   -> 불일치 {len(err)}건")
    return len(err)


if __name__ == "__main__":
    total = sum(check(p) for p in sys.argv[1:])
    sys.exit(1 if total else 0)
