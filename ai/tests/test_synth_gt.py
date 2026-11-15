"""생성기 v2 정답(ground_truth.json) → 평가 스크립트(backend/evaluation) 정답 라벨 변환."""
import json

import pytest

from tools.synth_gt import convert


def _item(item_id, result, *, value_type="exact", expected="PASS", reason="OK", unit="ppm", value_std=None):
    return {"item_id": item_id, "printed_name": item_id, "unit": unit, "result": result, "value_type": value_type,
            "value_std": value_std, "expected": expected, "reason": reason}


def _doc(doc_id, template, *, fields, items, lot="ACCEPT", reason_codes=(), split="dev"):
    stem = doc_id
    return {"doc_id": doc_id, "template": template, "split": split, "supplier": "Corvane Lithium Refining Pty Ltd",
            "fields": fields, "items": items, "lot_recommendation": lot, "reason_codes": list(reason_codes),
            "variants": [f"pdf/{split}/original/{stem}.pdf", f"pdf/{split}/lowres/{stem}_lowres.pdf"]}


def _write(tmp_path, docs, material_key="li2co3"):
    gen = tmp_path / "gen"
    gen.mkdir()
    (gen / "ground_truth.json").write_text(json.dumps({"material_key": material_key, "documents": docs}), encoding="utf-8")
    return gen


def _load(out, stem):
    return json.loads((out / f"{stem}.json").read_text(encoding="utf-8"))


def test_each_variant_gets_its_own_label(tmp_path):
    gen = _write(tmp_path, [_doc("COA_D_0001", "D", fields={"lot_no": "KC25-277-01"}, items=[])])
    stems = convert(gen, tmp_path / "gt")
    assert stems == ["COA_D_0001", "COA_D_0001_lowres"]
    gt = _load(tmp_path / "gt", "COA_D_0001_lowres")
    # 평가 스크립트는 파일 이름(document_id)으로 출력과 짝짓고, 아래 네 칸으로 나눠 보고한다
    assert gt["document_id"] == "COA_D_0001_lowres"
    assert (gt["material_code"], gt["source"], gt["form"], gt["degradation"]) == ("LI2CO3", "synthetic", "D", "lowres")
    assert gt["split"] == "dev"


def test_item_names_and_labels_follow_server_names(tmp_path):
    items = [
        _item("na", "42.8 ppm", value_std=42.8),
        _item("li2co3", "99.71", unit="%", value_std=99.71),
        _item("so4", "<10", value_type="bound", reason="BOUND_WITHIN_LIMIT", value_std=10.0),
        _item("heavy_metals", "0.0004 %", value_type="ambiguous", expected="CHECK", reason="AMBIGUOUS_ANALYTE"),
        _item("k", "N.D. (LOD 20 ppm)", value_type="nd", expected="INDETERMINATE", reason="ND_WITH_LOD"),
        _item("ni", "3.1", expected="REF", reason="REF"),
        _item("appearance", "Conforms", value_type="text", unit="—"),
        _item("mg", "", value_type="missing", expected="MISSING", reason="MISSING_REQUIRED"),
        _item("cu", "", value_type="derived", expected="CHECK", reason="AMBIGUOUS_ANALYTE"),
    ]
    gen = _write(tmp_path, [_doc("COA_A_0001", "A", fields={}, items=items)])
    convert(gen, tmp_path / "gt")
    got = {i["normalized_name"]: i for i in _load(tmp_path / "gt", "COA_A_0001")["items"]}

    assert got["Na"] == {"normalized_name": "Na", "raw_value": "42.8 ppm", "unit": "ppm", "converted_value": 42.8,
                         "judgement": "pass", "reason_code": None}
    assert got["순도"]["raw_value"] == "99.71"
    assert got["황산염"]["reason_code"] is None                 # 보고한계가 상한 이하인 '<' 는 적합, 사유 없음
    assert (got["중금속 총량"]["judgement"], got["중금속 총량"]["reason_code"]) == ("check", "AMBIGUOUS_ANALYTE")
    assert (got["K"]["judgement"], got["K"]["reason_code"]) == ("undetermined", "LOD_ABOVE_LIMIT")
    assert "judgement" not in got["Ni"] and "reason_code" not in got["Ni"]  # 사내 규격 없는 참고 항목: 판정 채점 안 함
    assert got["외관"]["unit"] is None
    assert got["Mg"] == {"normalized_name": "Mg", "judgement": "missing", "reason_code": "MISSING_REQUIRED"}
    assert "Cu" not in got                                     # 표에 없는 유도 줄은 추출 대상이 아니다


def test_header_dates_lot_recommendation_and_document_issues(tmp_path):
    docs = [
        _doc("COA_D_0002", "D", fields={"lot_no": "KC25-277-02", "test_date": "10/05/2025"}, items=[],
             lot="HOLD", reason_codes=["OUT_OF_SPEC", "DATE_CONFLICT", "MATERIAL_MISMATCH"]),
        _doc("COA_A_0002", "A", fields={"lot_no": "AL2510006", "issue_date": "07-Oct-2025"}, items=[], lot="REJECT"),
        _doc("COA_B_0002", "B", fields={"lot_no": "LC25100401", "test_date": "2025-10-05"}, items=[]),
    ]
    convert(_write(tmp_path, docs), tmp_path / "gt")
    d = _load(tmp_path / "gt", "COA_D_0002")
    assert d["header"] == {"supplier": "Corvane Lithium Refining Pty Ltd", "lot_no": "KC25-277-02", "test_date": "2025-10-05"}
    assert d["lot_recommendation"] == "hold"
    assert d["document_issues"] == ["DATE_CONFLICT", "PRODUCT_MISMATCH"]  # 항목 사유코드는 문서 사유가 아니다
    a = _load(tmp_path / "gt", "COA_A_0002")
    assert "test_date" not in a["header"]                      # 시험일 칸이 없는 양식은 채점하지 않는다
    assert a["lot_recommendation"] == "reject"
    assert _load(tmp_path / "gt", "COA_B_0002")["header"]["test_date"] == "2025-10-05"


def test_unknown_item_id_is_rejected(tmp_path):
    gen = _write(tmp_path, [_doc("COA_A_0003", "A", fields={}, items=[_item("lithium_oxide", "1.0")])])
    with pytest.raises(ValueError, match="lithium_oxide"):
        convert(gen, tmp_path / "gt")
