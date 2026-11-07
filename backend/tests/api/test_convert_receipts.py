"""[담당: 홍채령] 생성기 v2 receipts.csv 변환기 테스트 (tools/convert_receipts.py, 10.25 회의 결정 5).

변환 규칙은 DB 없이 확인하고, 변환한 CSV 를 서버 입고 CSV 검사(batch_service.parse_receipts_csv)가 받는지는 DB 로 확인한다.
"""
import csv

import pytest

from app.services import batch_service
from seeds.seed_specs import seed_specs
from tools.convert_receipts import SERVER_COLUMNS, ConvertError, convert_file, load_spec_sets, main

# 생성기 coa_common.save_labels 가 쓰는 열 순서와 표기 그대로
GENERATOR_CSV = """receipt_id,supplier,material,received_lot,spec_id,received_date
RCV-2510-0001,Jiangxi Chengxin Lithium,Li2CO3 Battery Grade,CX2509-0107,SYD-QS-LC-BG v1,2025-10-03
RCV-2510-0002,"Nanotrun, Ltd.",Li2CO3 Battery Grade,NT-250918-02,SYD-QS-LC-BG v1,2025-10-05
RCV-2510-0003,Jiangxi Chengxin Lithium,LiOH·H2O Battery Grade,CX2509-0233,SYD-QS-LHM-BG v1,2025-10-07
"""


def write(tmp_path, text, name="receipts.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8-sig")
    return path


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_spec_sets_mapping_from_seed():
    mapping = load_spec_sets()
    assert mapping["SYD-QS-LC-BG v1"] == ("LI2CO3-GENV2-EVAL", "LI2CO3")
    assert mapping["SYD-QS-LHM-BG v1"] == ("LIOH-BG-V1", "LIOH")
    assert mapping["YS/T 582-2023"] is None                             # D1·DEMO-R·D3 가 같은 버전이라 못 정함


def test_convert_generator_receipts(tmp_path):
    dst = tmp_path / "out.csv"
    rows = convert_file(write(tmp_path, GENERATOR_CSV), dst)

    assert len(rows) == 3
    out = read(dst)
    assert list(out[0].keys()) == SERVER_COLUMNS
    assert out[0] == {"receipt_id": "RCV-2510-0001", "supplier": "Jiangxi Chengxin Lithium", "material": "LI2CO3",
                      "received_lot": "CX2509-0107", "spec_id": "LI2CO3-GENV2-EVAL", "received_date": "2025-10-03"}
    assert out[1]["supplier"] == "Nanotrun, Ltd."                       # 쉼표 있는 이름도 그대로
    # 생성기의 입고 원자재 불일치(MATERIAL_MISMATCH) 행: 원자재와 규격 모두 수산화리튬으로 바뀐다
    assert (out[2]["material"], out[2]["spec_id"]) == ("LIOH", "LIOH-BG-V1")


def test_unknown_spec_id_and_blank_lot_report_lines(tmp_path):
    text = GENERATOR_CSV + "RCV-X,Foo,Li2CO3 Battery Grade,L-9,SYD-QS-LC-BG v9,2025-10-09\nRCV-Y,Foo,,,SYD-QS-LC-BG v1,\n"
    with pytest.raises(ConvertError) as e:
        convert_file(write(tmp_path, text), tmp_path / "out.csv")
    assert "5행" in str(e.value) and "SYD-QS-LC-BG v9" in str(e.value)
    assert "6행" in str(e.value)
    with pytest.raises(ConvertError, match="여러 개"):
        convert_file(write(tmp_path, GENERATOR_CSV + "RCV-Z,Foo,x,L-8,YS/T 582-2023,\n"), tmp_path / "out.csv")
    assert not (tmp_path / "out.csv").exists()                          # 오류면 파일을 만들지 않는다


def test_not_a_generator_file(tmp_path):
    with pytest.raises(ConvertError, match="spec_id"):
        convert_file(write(tmp_path, "receipt_id,received_lot\nR1,L1\n"), tmp_path / "out.csv")


def test_cli(tmp_path, capsys):
    dst = tmp_path / "out.csv"
    assert main([str(write(tmp_path, GENERATOR_CSV)), str(dst)]) == 0
    assert "3행 변환" in capsys.readouterr().out
    assert main([str(write(tmp_path, "receipt_id\nR1\n", "bad.csv")), str(dst)]) == 1


def test_converted_csv_is_accepted_by_server(db, tmp_path):
    """변환 결과를 서버 입고 CSV 검사에 그대로 넣으면 통과한다 (규격 세트 코드가 DB 에 있음)."""
    seed_specs(db)
    db.commit()
    dst = tmp_path / "out.csv"
    convert_file(write(tmp_path, GENERATOR_CSV), dst)

    rows = batch_service.parse_receipts_csv(db, dst.read_bytes(), default_material="LI2CO3")

    assert [(r.receipt_id, r.material, r.spec_id) for r in rows] == [
        ("RCV-2510-0001", "LI2CO3", "LI2CO3-GENV2-EVAL"),
        ("RCV-2510-0002", "LI2CO3", "LI2CO3-GENV2-EVAL"),
        ("RCV-2510-0003", "LIOH", "LIOH-BG-V1"),
    ]
