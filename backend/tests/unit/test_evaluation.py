"""[담당: 홍채령] 평가 스크립트 (evaluation/) 지표 계산"""
import json

import pytest

from evaluation.data import parse_ground_truth, parse_prediction
from evaluation.metrics import DocPair, classify_value_error, evaluate, value_match
from evaluation.data import GTItem, PredItem
from evaluation.report import build_report, to_markdown
from evaluation.run import main


def gt_doc(doc_id="D1", lot="reject", **extra):
    return parse_ground_truth({
        "document_id": doc_id,
        "material_code": "LI2CO3",
        "source": "real",
        "header": {"supplier": "Chengxin", "lot_no": "A0266047", "test_date": "2026-09-28"},
        "items": [
            {"normalized_name": "순도", "raw_value": "99.6 %", "converted_value": 99.6, "judgement": "pass", "reason_code": None},
            {"normalized_name": "Na", "raw_value": "2.56 ppm", "converted_value": 2.56, "judgement": "pass", "reason_code": None},
            {"normalized_name": "K", "raw_value": "< 100 ppm", "converted_value": 100, "judgement": "undetermined",
             "reason_code": "BOUND_ABOVE_LIMIT"},
            {"normalized_name": "Ca", "raw_value": "0.01 %", "converted_value": 100, "judgement": "fail",
             "reason_code": "OUT_OF_SPEC"},
            {"normalized_name": "황산염", "judgement": "missing", "reason_code": "MISSING_REQUIRED"},
        ],
        "lot_recommendation": lot,
        "document_issues": [],
        **extra,
    }, doc_id)


def pred_doc(doc_id="D1", **overrides):
    raw = {
        "document_id": doc_id,
        "supplier": "Chengxin", "lot_no": "A0266047", "test_date": "2026-09-28", "origin": None,
        "items": [
            {"normalized_name": "순도", "raw_value": "99.6 %", "converted_value": 99.6, "judgement": "pass", "confidence": 0.95},
            # AI 가 2.56 을 25.6 으로 오독, 신뢰도 낮음
            {"normalized_name": "Na", "raw_value": "25.6 ppm", "converted_value": 25.6, "judgement": "check",
             "reason_code": "LOW_CONFIDENCE", "confidence": 0.62},
            {"normalized_name": "K", "raw_value": "< 100 ppm", "converted_value": 100, "judgement": "undetermined",
             "reason_code": "BOUND_ABOVE_LIMIT", "confidence": 0.9},
            {"normalized_name": "Ca", "raw_value": "0.01 %", "converted_value": 100, "judgement": "fail",
             "reason_code": "OUT_OF_SPEC", "confidence": 0.85},
            {"normalized_name": "황산염", "judgement": "missing", "reason_code": "MISSING_REQUIRED", "mapping_source": "spec"},
        ],
        "document_issues": [],
        "lot_recommendation": "reject",
    }
    raw.update(overrides)
    return parse_prediction({"success": True, "data": raw, "error": None}, doc_id)


def test_extraction_and_judgement():
    r = evaluate([DocPair(gt_doc(), pred_doc())])
    ex, j = r["extraction"], r["judgement"]
    assert ex["items_on_coa"] == 4            # 누락 항목은 추출 대상이 아님
    assert ex["item_recall"] == 1.0
    assert ex["value_accuracy"] == 0.75       # Na 오독
    assert ex["error_types"] == {"unit": 1}   # 2.56 → 25.6 은 10배 차이
    assert ex["header_accuracy"] == 1.0
    assert ex["extra_items"] == 0
    assert j["accuracy"] == 0.8               # Na pass → check
    assert j["confusion"]["pass"] == {"pass": 1, "check": 1}
    assert (j["risky_missed"], j["hidden_fail_missed"]) == (0, 0)


def test_confidence_flags_errors():
    c = evaluate([DocPair(gt_doc(), pred_doc())])["confidence"]
    assert (c["low_items"], c["high_items"]) == (1, 3)
    assert c["flag_precision"] == 1.0   # 신뢰도 낮음 1개가 실제 오류
    assert c["flag_recall"] == 1.0      # 오류 1개가 모두 신뢰도 낮음으로 잡힘


def test_reason_code_precision_recall():
    rc = evaluate([DocPair(gt_doc(), pred_doc())])["reason_code"]
    # 정답 사유코드 3개 모두 맞힘. Na 의 LOW_CONFIDENCE 는 실행마다 달라지는 코드라 채점에서 뺀다
    assert rc["micro"] == {"tp": 3, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0}
    assert "LOW_CONFIDENCE" not in rc["per_code"]


def test_wrong_reason_code_is_fp_and_fn():
    pred = pred_doc()
    next(i for i in pred.items if i.normalized_name == "K").reason_code = "SPEC_COPIED"
    r = evaluate([DocPair(gt_doc(), pred)])
    assert r["reason_code"]["micro"] == {"tp": 2, "fp": 1, "fn": 1, "precision": 0.6667, "recall": 0.6667}
    assert r["judgement"]["low_confidence_checks"] == 1


def test_risky_misses_counted():
    items = pred_doc().items
    for it in items:
        if it.normalized_name in ("K", "Ca"):
            it.judgement, it.reason_code = "pass", None
    pred = pred_doc()
    pred.items = [it for it in items if it.normalized_name != "황산염"]  # 누락 항목도 못 만듦
    j = evaluate([DocPair(gt_doc(), pred)])["judgement"]
    assert j["risky_missed"] == 2        # K 판정 불가 → 적합, 황산염 누락 → 출력 없음
    assert j["hidden_fail_missed"] == 1  # Ca 부적합 → 적합
    assert j["confusion"]["missing"] == {"absent": 1}


def test_lot_rates():
    pairs = [
        DocPair(gt_doc("N1", lot="approve"), pred_doc("N1", lot_recommendation="approve")),
        DocPair(gt_doc("N2", lot="approve"), pred_doc("N2", lot_recommendation="hold")),
        DocPair(gt_doc("N3", lot="approve"), pred_doc("N3", lot_recommendation="approve")),
        DocPair(gt_doc("N4", lot="approve"), pred_doc("N4", lot_recommendation="reject")),
        DocPair(gt_doc("P1", lot="hold"), pred_doc("P1", lot_recommendation="approve")),
    ]
    lot = evaluate(pairs)["lot"]
    assert lot["auto_process_rate"] == 0.5    # 정상 4건 중 승인 권고 2건
    assert lot["over_hold_rate"] == 0.25
    assert lot["false_reject_rate"] == 0.25
    assert "unsafe_approve_rate" not in lot   # 로트 단위 위험 오류는 미확정이라 계산하지 않음
    assert lot["accuracy"] == 0.4


def test_unlabeled_fields_are_not_scored():
    gt = parse_ground_truth({"document_id": "U1", "items": [{"normalized_name": "Na", "raw_value": "12 ppm"}]}, "U1")
    pred = parse_prediction({"items": [{"normalized_name": "Na", "raw_value": "12 ppm", "reason_code": "X"}]}, "U1")
    r = evaluate([DocPair(gt, pred)])
    assert r["extraction"]["value_accuracy"] == 1.0
    assert r["judgement"]["items"] == 0 and r["judgement"]["accuracy"] is None
    assert r["reason_code"]["micro"]["fp"] == 0   # 라벨에 reason_code 가 없으면 채점하지 않음
    assert r["lot"]["documents"] == 0


def test_missing_prediction_counts_as_unrecognized():
    r = evaluate([DocPair(gt_doc(), None)])
    assert r["extraction"]["item_recall"] == 0.0
    assert r["extraction"]["header_accuracy"] == 0.0
    assert r["lot"]["confusion"] == {"reject": {"absent": 1}}


def test_document_issues():
    gt = gt_doc(document_issues=["LOT_MISMATCH"])
    di = evaluate([DocPair(gt, pred_doc(document_issues=[{"code": "DATE_CONFLICT", "message": "..."}]))])["document_issues"]
    assert di["micro"] == {"tp": 0, "fp": 1, "fn": 1, "precision": 0.0, "recall": 0.0}


@pytest.mark.parametrize("g_raw, p_raw, g_val, p_val, expected", [
    ("< 20 ppm", "20 ppm", 20, 20, "qualifier"),
    ("0.002 %", "0.002 %", 20, 0.002, "unit"),
    ("3.32", "3.82", 3.32, 3.82, "number"),
])
def test_classify_value_error(g_raw, p_raw, g_val, p_val, expected):
    g = GTItem(normalized_name="x", raw_value=g_raw, converted_value=g_val)
    p = PredItem(normalized_name="x", raw_value=p_raw, converted_value=p_val)
    assert value_match(g, p) is False
    assert classify_value_error(g, p) == expected


def test_raw_value_comparison_normalizes_symbols():
    g = GTItem(normalized_name="x", raw_value="≤ 5 ppm")
    assert value_match(g, PredItem(normalized_name="x", raw_value="=<5ppm")) is True


def test_report_groups_and_baseline():
    gt = {"D1": gt_doc("D1"), "D2": gt_doc("D2", source="synthetic", material_code="LIOH")}
    system = {"D1": pred_doc("D1"), "D2": pred_doc("D2")}
    baseline = {"D1": pred_doc("D1", lot_recommendation="approve")}   # D2 출력 없음
    rep = build_report(gt, system, baseline, 0.8, meta={"gt": "g", "pred": "p", "baseline": "b", "policy": {}})
    assert set(rep["system"]["groups"]["source"]) == {"real", "synthetic"}
    assert set(rep["system"]["groups"]["material_code"]) == {"LI2CO3", "LIOH"}
    assert rep["baseline"]["missing_predictions"] == ["D2"]
    lot_row = next(r for r in rep["comparison"] if r["metric"] == "로트 권고 일치율")
    assert (lot_row["system"], lot_row["baseline"], lot_row["delta"]) == (1.0, 0.0, 1.0)
    md = to_markdown(rep)
    assert "규칙 베이스라인 비교" in md and "실물/합성별" in md and "D2" in md


def test_cli_writes_report(tmp_path):
    (tmp_path / "gt").mkdir()
    (tmp_path / "pred").mkdir()
    (tmp_path / "gt" / "D1.json").write_text(json.dumps(gt_doc().model_dump(mode="json")), encoding="utf-8")
    (tmp_path / "pred" / "D1.json").write_text(json.dumps(pred_doc().model_dump(mode="json")), encoding="utf-8")
    out = main(["--gt", str(tmp_path / "gt"), "--pred", str(tmp_path / "pred"), "--out", str(tmp_path / "out")])
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["system"]["overall"]["extraction"]["item_recall"] == 1.0
    assert report["meta"]["policy"]["LOW_CONFIDENCE_THRESHOLD"] == 0.8
    assert (out / "report.md").read_text(encoding="utf-8").startswith("# CoA 추출·판정 평가 리포트")

