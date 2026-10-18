"""[담당: 홍채령] 평가 리포트: 전체·그룹별 지표, 규칙 베이스라인 비교, JSON·마크다운 출력."""
from datetime import datetime

from evaluation.data import GTDocument, PredDocument
from evaluation.metrics import DocPair, evaluate

# 분리 보고 기준. 원자재별·실물/합성별: 업무 분담 v1.4 요청 / 양식별·열화 단계별: 업무 분담 '평가'
GROUP_BY = ("material_code", "source", "form", "degradation")

# 비교표·그룹표에 보이는 핵심 지표 (경로, 표시 이름, 높을수록 좋은지)
# 기획안 v2 에만 있는 지표(로트 단위 위험 오류, 값 유형, 매핑, 목표값 등)는 미확정이라 넣지 않았다 (2026-10-18)
KEY_METRICS = [
    (("extraction", "item_recall"), "항목 인식률", True),
    (("extraction", "value_accuracy"), "수치 일치율", True),
    (("extraction", "header_accuracy"), "머리글 일치율", True),
    (("judgement", "accuracy"), "판정 일치율 (5종)", True),
    (("judgement", "risky_missed"), "판정 불가·누락 → 적합 (항목, 건)", False),
    (("judgement", "hidden_fail_missed"), "부적합 → 적합 (항목, 건)", False),
    (("lot", "accuracy"), "로트 권고 일치율", True),
    (("lot", "auto_process_rate"), "정상 자동 처리율", True),
    (("lot", "over_hold_rate"), "과잉 보류율", False),
    (("reason_code", "micro", "precision"), "사유코드 정밀도", True),
    (("reason_code", "micro", "recall"), "사유코드 재현율", True),
]


def _get(d: dict, path: tuple):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def evaluate_all(gt: dict[str, GTDocument], preds: dict[str, PredDocument], threshold: float) -> dict:
    pairs = [DocPair(g, preds.get(doc_id)) for doc_id, g in sorted(gt.items())]
    groups = {}
    for field in GROUP_BY:
        buckets: dict[str, list[DocPair]] = {}
        for p in pairs:
            value = getattr(p.gt, field)
            if value is not None:
                buckets.setdefault(value, []).append(p)
        if buckets:
            groups[field] = {v: evaluate(ps, threshold) for v, ps in sorted(buckets.items())}
    return {
        "missing_predictions": sorted(set(gt) - set(preds)),
        "extra_predictions": sorted(set(preds) - set(gt)),
        "overall": evaluate(pairs, threshold),
        "groups": groups,
    }


def compare(system: dict, baseline: dict) -> list[dict]:
    rows = []
    for path, label, higher_better in KEY_METRICS:
        s, b = _get(system["overall"], path), _get(baseline["overall"], path)
        delta = round(s - b, 4) if s is not None and b is not None else None
        rows.append({"metric": label, "system": s, "baseline": b, "delta": delta, "higher_is_better": higher_better})
    return rows


def build_report(gt, preds, baseline, threshold: float, meta: dict) -> dict:
    report = {
        "meta": {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "documents": len(gt), "threshold": threshold, **meta},
        "system": evaluate_all(gt, preds, threshold),
    }
    if baseline is not None:
        report["baseline"] = evaluate_all(gt, baseline, threshold)
        report["comparison"] = compare(report["system"], report["baseline"])
    return report


# ---------------------------------------------------------------------------
# 마크다운
# ---------------------------------------------------------------------------
def _fmt(v, as_count=False) -> str:
    if v is None:
        return "-"
    if as_count or isinstance(v, int):
        return str(v)
    return f"{v * 100:.1f}%"


def _key_table(results: dict[str, dict]) -> list[str]:
    names = list(results)
    lines = ["| 지표 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for path, label, _ in KEY_METRICS:
        lines.append(f"| {label} | " + " | ".join(_fmt(_get(results[n], path)) for n in names) + " |")
    lines.append("| 문서 수 | " + " | ".join(str(results[n]["documents"]) for n in names) + " |")
    return lines


def _confusion_table(conf: dict, title: str) -> list[str]:
    if not conf:
        return []
    cols = sorted({p for row in conf.values() for p in row})
    lines = [f"**{title}** (행: 정답, 열: 시스템)", "", "| 정답 \\ 시스템 | " + " | ".join(cols) + " |",
             "|---|" + "---|" * len(cols)]
    for g in sorted(conf):
        lines.append(f"| {g} | " + " | ".join(str(conf[g].get(c, 0)) for c in cols) + " |")
    return lines + [""]


def _prf_table(prf: dict, title: str) -> list[str]:
    if not prf["per_code"]:
        return []
    lines = [f"**{title}**", "", "| 코드 | TP | FP | FN | 정밀도 | 재현율 |", "|---|---|---|---|---|---|"]
    for code, r in prf["per_code"].items():
        lines.append(f"| {code} | {r['tp']} | {r['fp']} | {r['fn']} | {_fmt(r['precision'])} | {_fmt(r['recall'])} |")
    m = prf["micro"]
    lines.append(f"| **전체** | {m['tp']} | {m['fp']} | {m['fn']} | {_fmt(m['precision'])} | {_fmt(m['recall'])} |")
    return lines + [""]


def to_markdown(report: dict) -> str:
    meta, sysr = report["meta"], report["system"]
    o = sysr["overall"]
    out = ["# CoA 추출·판정 평가 리포트", "",
           f"- 생성: {meta['generated_at']}",
           f"- 정답 라벨: `{meta.get('gt')}` ({meta['documents']}건)",
           f"- 시스템 출력: `{meta.get('pred')}`" + (f" / 베이스라인: `{meta['baseline']}`" if meta.get("baseline") else ""),
           f"- 신뢰도 기준값: {meta['threshold']}"]
    if meta.get("policy"):
        out.append("- 판정 정책 설정: " + ", ".join(f"`{k}={v}`" for k, v in meta["policy"].items()))
    if sysr["missing_predictions"]:
        out.append(f"- ⚠️ 시스템 출력이 없는 문서 {len(sysr['missing_predictions'])}건 (항목 미인식으로 계산): "
                   + ", ".join(sysr["missing_predictions"]))
    if report.get("baseline", {}).get("missing_predictions"):
        miss = report["baseline"]["missing_predictions"]
        out.append(f"- ⚠️ 베이스라인 출력이 없는 문서 {len(miss)}건: " + ", ".join(miss))
    if sysr["extra_predictions"]:
        out.append(f"- 정답 라벨이 없어 제외한 출력 {len(sysr['extra_predictions'])}건: " + ", ".join(sysr["extra_predictions"]))

    out += ["", "## 1. 전체 지표", ""] + _key_table({"전체": o})

    if "comparison" in report:
        out += ["", "## 2. 규칙 베이스라인 비교 (시스템 − 베이스라인)", "",
                "| 지표 | 시스템 | 베이스라인 | 차이 |", "|---|---|---|---|"]
        for r in report["comparison"]:
            d = r["delta"]
            better = d is not None and d != 0 and ((d > 0) == r["higher_is_better"])
            mark = " ✅" if better else (" ⚠️" if d not in (None, 0) else "")
            is_count = isinstance(r["system"], int) or isinstance(r["baseline"], int)
            dtxt = "-" if d is None else (f"{d:+d}" if is_count else f"{d * 100:+.1f}%p")
            out.append(f"| {r['metric']} | {_fmt(r['system'])} | {_fmt(r['baseline'])} | {dtxt}{mark} |")

    if sysr["groups"]:
        out += ["", "## 3. 분리 보고", ""]
        titles = {"material_code": "원자재별", "source": "실물/합성별", "form": "양식별", "degradation": "열화 단계별"}
        for field, results in sysr["groups"].items():
            out += [f"### {titles.get(field, field)}", ""] + _key_table(results) + [""]

    ex, cf = o["extraction"], o["confidence"]
    out += ["## 4. 상세", "",
            f"- 추출 대상 항목 {ex['items_on_coa']}개, 정답에 없는 항목 출력 {ex['extra_items']}개, "
            f"수치 비교 {ex['value_evaluated']}개, 머리글 필드 {ex['header_fields']}개",
            f"- 신뢰도 낮음(LOW_CONFIDENCE)으로 확인 필요가 된 항목 {o['judgement']['low_confidence_checks']}개 "
            "(판정 일치율에서는 불일치로 세고, 사유코드 채점에서는 뺌)",
            "- 오류 유형: " + (", ".join(f"{k} {v}" for k, v in sorted(ex["error_types"].items())) or "없음"),
            f"- 신뢰도 검증 (기준 {cf['threshold']}): 낮음 {cf['low_items']}개 중 오류 {_fmt(cf['error_rate_low'])}, "
            f"높음 {cf['high_items']}개 중 오류 {_fmt(cf['error_rate_high'])}, 실제 오류 중 낮음으로 잡힘 {_fmt(cf['flag_recall'])}",
            ""]
    out += _confusion_table(o["judgement"]["confusion"], "항목 판정 혼동행렬")
    out += _confusion_table(o["lot"]["confusion"], "로트 권고 혼동행렬")
    out += _prf_table(o["reason_code"], "사유코드")
    out += _prf_table(o["document_issues"], "문서 정합성 (document_issues)")
    return "\n".join(out) + "\n"
