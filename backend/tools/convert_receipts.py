"""[담당: 홍채령] 가상 CoA 생성기 v2 receipts.csv → 일괄 접수(POST /documents/batch) 입고 CSV 변환 (10.25 회의 결정 5)

생성기 receipts.csv 는 원자재와 규격을 생성기 표기로 적는다. 서버는 원자재 코드와 규격 세트 코드를 받는다.

    생성기                                서버
    material = Li2CO3 Battery Grade      material = LI2CO3
    spec_id  = SYD-QS-LC-BG v1           spec_id  = LI2CO3-GENV2-EVAL
    material = LiOH·H2O Battery Grade    material = LIOH
    spec_id  = SYD-QS-LHM-BG v1          spec_id  = LIOH-BG-V1

규격 세트는 seeds/data/spec_sets.csv 의 version 칸(생성기 spec_id 와 같은 값)으로 찾고, 원자재 코드는 그 세트의
material_code 를 쓴다. 그래서 원자재 이름 표를 따로 두지 않는다. 생성기가 일부러 넣은 입고 원자재 불일치
(MATERIAL_MISMATCH) 행은 spec_id 도 다른 원자재 것이라 그대로 PRODUCT_MISMATCH 로 이어진다.
receipt_id, supplier, received_lot, received_date 는 그대로 옮긴다.

사용법 (backend 폴더에서, DB 필요 없음)
    python -m tools.convert_receipts <생성기 receipts.csv> <저장할 csv>
    python -m tools.convert_receipts out_A_li2co3/receipts.csv receipts_server.csv
"""
import argparse
import csv
import sys
from pathlib import Path

SPEC_SETS_CSV = Path(__file__).resolve().parent.parent / "seeds" / "data" / "spec_sets.csv"
SERVER_COLUMNS = ["receipt_id", "supplier", "material", "received_lot", "spec_id", "received_date"]
MAX_ROWS = 200  # 서버 일괄 접수 한 번에 받는 입고 행 수 (batch_service.MAX_RECEIPT_ROWS)


class ConvertError(Exception):
    pass


def load_spec_sets(path: Path = SPEC_SETS_CSV) -> dict[str, tuple[str, str] | None]:
    """{규격 버전(생성기 spec_id): (세트 코드, 원자재 코드)}.

    같은 버전을 쓰는 세트가 여럿이면(예: YS/T 582-2023 의 D1·D3) 하나로 정할 수 없어 None 으로 둔다.
    생성기 spec_id 는 세트마다 하나뿐이라 영향이 없고, 그런 버전이 receipts.csv 에 나오면 그 행을 오류로 알린다.
    """
    mapping: dict[str, tuple[str, str] | None] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            version = (row.get("version") or "").strip()
            if not version:
                continue
            mapping[version] = None if version in mapping else (row["code"].strip(), row["material_code"].strip())
    return mapping


def convert_rows(rows: list[dict], spec_sets: dict[str, tuple[str, str] | None]) -> list[dict]:
    """생성기 행 → 서버 행. 모르는 spec_id 나 빈 필수 칸이 있으면 줄 번호를 모아 ConvertError."""
    out, errors = [], []
    for line, row in enumerate(rows, start=2):
        values = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if not any(values.values()):
            continue
        if not values.get("receipt_id") or not values.get("received_lot"):
            errors.append(f"{line}행: receipt_id, received_lot 이 비어 있습니다")
            continue
        spec_id = values.get("spec_id", "")
        if spec_id not in spec_sets:
            errors.append(f"{line}행: 서버에 없는 규격 {spec_id!r} (seeds/data/spec_sets.csv 의 version 칸에 없음)")
            continue
        if spec_sets[spec_id] is None:
            errors.append(f"{line}행: 규격 {spec_id!r} 을 쓰는 세트가 여러 개라 하나로 정할 수 없습니다")
            continue
        set_code, material_code = spec_sets[spec_id]
        out.append({
            "receipt_id": values["receipt_id"],
            "supplier": values.get("supplier", ""),
            "material": material_code,
            "received_lot": values["received_lot"],
            "spec_id": set_code,
            "received_date": values.get("received_date", ""),
        })
    if errors:
        raise ConvertError("\n".join(errors))
    return out


def convert_file(src: Path, dst: Path, spec_sets_path: Path = SPEC_SETS_CSV) -> list[dict]:
    with open(src, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in ("receipt_id", "received_lot", "spec_id") if c not in (reader.fieldnames or [])]
        if missing:
            raise ConvertError(f"{src} 에 {', '.join(missing)} 열이 없습니다. 생성기 receipts.csv 가 맞는지 확인하세요")
        rows = convert_rows(list(reader), load_spec_sets(spec_sets_path))
    # 서버가 UTF-8(BOM 포함)을 읽는다. 엑셀에서 열어도 한글이 깨지지 않게 BOM 을 붙인다
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SERVER_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="생성기 v2 receipts.csv 를 일괄 접수 입고 CSV 로 바꾼다")
    ap.add_argument("src", type=Path, help="생성기 receipts.csv")
    ap.add_argument("dst", type=Path, help="저장할 입고 CSV")
    args = ap.parse_args(argv)
    try:
        rows = convert_file(args.src, args.dst)
    except ConvertError as e:
        print(f"변환 실패:\n{e}", file=sys.stderr)
        return 1
    print(f"{len(rows)}행 변환 → {args.dst}")
    if len(rows) > MAX_ROWS:
        print(f"주의: 일괄 접수는 입고 행 {MAX_ROWS}개까지 받습니다. 올릴 CoA 의 행만 남겨서 나눠 올리세요", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
