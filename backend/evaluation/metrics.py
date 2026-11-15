"""[담당: 홍채령] 평가 지표 계산.

evaluate(pairs) 하나가 문서 묶음 하나의 지표를 모두 계산한다. 그룹별(원자재, 실물/합성 등) 보고는
report.py 가 문서를 나눠 evaluate 를 여러 번 부른다. 분모가 0 인 비율은 None (0 과 구분).
정의는 README '지표 정의' 와 같다.
"""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from app.core.enums import Judgement, LotRecommendation

from evaluation.data import GTDocument, GTItem, PredDocument, PredItem

ABSENT = "absent"  # 시스템 출력에 해당 항목·값이 없음
# 실행마다 달라져 정답 라벨에 적을 수 없는 사유코드. 사유코드 채점에서 빼고 개수만 따로 센다.
RUN_DEPENDENT_CODES = {"LOW_CONFIDENCE"}
RISKY_MISSED = {Judgement.UNDETERMINED, Judgement.MISSING}  # 적합으로 넘기면 위험한 정답 판정
PASS_LIKE = {Judgement.PASS.value, ABSENT}

_QUALIFIER = re.compile(r"(<|≤|≦|=<|<=|\bn\.?d\.?\b|not\s*detected|none\s*detected|검출|불검출|未检出)", re.I)


@dataclass
class DocPair:
    gt: GTDocument
    pred: PredDocument | None  # None: 시스템 출력 파일 없음


def ratio(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None


def _norm_text(v: object) -> str:
    s = str(v).casefold().strip()
    s = s.replace("≤", "<=").replace("≦", "<=").replace("=<", "<=").replace("≥", ">=")
    return re.sub(r"\s+", "", s)


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name.casefold().strip())


def match_items(gt_items: list[GTItem], pred_items: list[PredItem]) -> tuple[list[tuple[GTItem, PredItem | None]], list[PredItem]]:
    """항목명(normalized_name)으로 정답과 출력을 짝짓는다. 같은 이름이 여러 개면 순서대로."""
    pool: dict[str, list[PredItem]] = defaultdict(list)
    for p in pred_items:
        pool[_key(p.normalized_name)].append(p)
    pairs = [(g, pool[_key(g.normalized_name)].pop(0) if pool[_key(g.normalized_name)] else None) for g in gt_items]
    extras = [p for ps in pool.values() for p in ps]
    return pairs, extras


def value_match(gt: GTItem, pred: PredItem) -> bool | None:
    """값 일치 여부. 환산값이 둘 다 숫자면 숫자로, 아니면 원문을 정리해 비교. 정답에 값이 없으면 None.

    "< 20" 과 "20" 처럼 부등호·검출 안 됨 표기가 다르면 숫자가 같아도 불일치다 (판정이 달라진다).
    """
    if gt.raw_value is not None and pred.raw_value is not None and _has_qualifier(gt.raw_value) != _has_qualifier(pred.raw_value):
        return False
    g, p = gt.converted_value, pred.converted_value
    if isinstance(g, (int, float)) and isinstance(p, (int, float)):
        return math.isclose(g, p, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(g, str) and isinstance(p, str):
        return _norm_text(g) == _norm_text(p)
    if gt.raw_value is not None:
        return pred.raw_value is not None and _norm_text(gt.raw_value) == _norm_text(pred.raw_value)
    return None


def _has_qualifier(raw: str | None) -> bool:
    return bool(_QUALIFIER.search(raw or ""))


def classify_value_error(gt: GTItem, pred: PredItem) -> str:
    """값 불일치 원인 (오류 분석용, 대략적인 분류)."""
    if _has_qualifier(gt.raw_value) != _has_qualifier(pred.raw_value):
        return "qualifier"      # 부등호·검출 안 됨 표기를 놓치거나 잘못 붙임
    g, p = gt.converted_value, pred.converted_value
    if isinstance(g, (int, float)) and isinstance(p, (int, float)) and g and p:
        k = math.log10(abs(p / g))
        if abs(k - round(k)) < 1e-6 and round(k) != 0:
            return "unit"       # 10의 거듭제곱 배 차이 (% ↔ ppm 환산 등)
    if pred.raw_value is None and pred.converted_value is None:
        return "value_missing"
    return "number"             # 숫자 오독 (예: 2.56 → 25.6)


def _header_score(gt: GTDocument, pred: PredDocument | None) -> tuple[int, int]:
    total = correct = 0
    for k, v in gt.header.items():
        if v is None:
            continue
        total += 1
        pv = pred.header.get(k) if pred else None
        correct += pv is not None and _norm_text(pv) == _norm_text(v)
    return correct, total


def _prf(tp: Counter, fp: Counter, fn: Counter) -> dict:
    codes = sorted(set(tp) | set(fp) | set(fn))
    per = {c: {"tp": tp[c], "fp": fp[c], "fn": fn[c],
               "precision": ratio(tp[c], tp[c] + fp[c]), "recall": ratio(tp[c], tp[c] + fn[c])} for c in codes}
    TP, FP, FN = sum(tp.values()), sum(fp.values()), sum(fn.values())
    return {"micro": {"tp": TP, "fp": FP, "fn": FN, "precision": ratio(TP, TP + FP), "recall": ratio(TP, TP + FN)},
            "per_code": per}


def evaluate(pairs: list[DocPair], threshold: float = 0.8) -> dict:
    n_items_on_coa = n_recognized = n_extra = 0
    n_value_total = n_value_ok = 0
    header_ok = header_total = 0
    judge_total = judge_ok = 0
    confusion: dict[str, Counter] = defaultdict(Counter)
    risky_missed = hidden_fail_missed = low_conf_checks = 0
    errors = Counter()
    conf = Counter()  # low/high × ok/err
    r_tp, r_fp, r_fn = Counter(), Counter(), Counter()
    i_tp, i_fp, i_fn = Counter(), Counter(), Counter()
    lot_conf: dict[str, Counter] = defaultdict(Counter)

    for pair in pairs:
        gt, pred = pair.gt, pair.pred
        item_pairs, extras = match_items(gt.items, pred.items if pred else [])
        n_extra += sum(1 for p in extras if p.mapping_source != "spec")

        c, t = _header_score(gt, pred)
        header_ok, header_total = header_ok + c, header_total + t

        reason_labeled = False
        for g, p in item_pairs:
            on_coa = g.judgement != Judgement.MISSING  # 누락 항목은 CoA 에 없으므로 추출 대상이 아니다
            if on_coa:
                n_items_on_coa += 1
                if p is None:
                    errors["item_not_recognized"] += 1
                else:
                    n_recognized += 1
                    ok = value_match(g, p)
                    if ok is not None:
                        n_value_total += 1
                        n_value_ok += ok
                        if not ok:
                            errors[classify_value_error(g, p)] += 1
                        if p.confidence is not None:
                            conf[("low" if p.confidence < threshold else "high", "ok" if ok else "err")] += 1

            if gt.item_labeled(g, "judgement") and g.judgement is not None:
                pj = (p.judgement if p and p.judgement else ABSENT)
                judge_total += 1
                judge_ok += pj == g.judgement.value
                confusion[g.judgement.value][pj] += 1
                if pj in PASS_LIKE and g.judgement in RISKY_MISSED:
                    risky_missed += 1
                if pj in PASS_LIKE and g.judgement == Judgement.FAIL:
                    hidden_fail_missed += 1

            if p and p.reason_code in RUN_DEPENDENT_CODES:
                low_conf_checks += 1
            if gt.item_labeled(g, "reason_code"):
                reason_labeled = True
                gc, pc = g.reason_code, (p.reason_code if p else None)
                if pc in RUN_DEPENDENT_CODES:
                    pc = None
                if gc and pc and gc == pc:
                    r_tp[gc] += 1
                else:
                    if pc:
                        r_fp[pc] += 1
                    if gc:
                        r_fn[gc] += 1
        if reason_labeled:  # 정답에 없는 항목에 붙은 사유코드는 오탐
            for p in extras:
                if p.reason_code and p.reason_code not in RUN_DEPENDENT_CODES:
                    r_fp[p.reason_code] += 1

        if gt.labeled("document_issues"):
            g_set, p_set = set(gt.document_issues), set(pred.document_issues if pred else [])
            for code in g_set & p_set:
                i_tp[code] += 1
            for code in p_set - g_set:
                i_fp[code] += 1
            for code in g_set - p_set:
                i_fn[code] += 1

        if gt.lot_recommendation is not None:
            lot_conf[gt.lot_recommendation.value][(pred.lot_recommendation if pred and pred.lot_recommendation else ABSENT)] += 1

    return {
        "documents": len(pairs),
        "extraction": {
            "items_on_coa": n_items_on_coa,
            "item_recall": ratio(n_recognized, n_items_on_coa),            # 항목 인식률
            "extra_items": n_extra,                                         # 정답에 없는 항목을 출력한 수
            "value_accuracy": ratio(n_value_ok, n_value_total),             # 수치 일치율 (인식한 항목 중)
            "value_evaluated": n_value_total,
            "header_accuracy": ratio(header_ok, header_total),              # 머리글 일치율
            "header_fields": header_total,
            "error_types": dict(errors),
        },
        "judgement": {
            "items": judge_total,
            "accuracy": ratio(judge_ok, judge_total),                       # 판정 일치율 (5종)
            "risky_missed": risky_missed,           # 판정 불가·누락을 적합으로 넘김 (가장 위험)
            "hidden_fail_missed": hidden_fail_missed,  # 부적합을 적합으로 넘김 (숨은 불합격 미탐)
            "low_confidence_checks": low_conf_checks,  # 신뢰도 낮음으로 확인 필요가 된 항목 (일치율 해석 참고용)
            "confusion": {g: dict(c) for g, c in confusion.items()},
        },
        "confidence": _confidence_report(conf, threshold),
        "reason_code": _prf(r_tp, r_fp, r_fn),
        "document_issues": _prf(i_tp, i_fp, i_fn),
        "lot": _lot_report(lot_conf),
    }


def _confidence_report(c: Counter, threshold: float) -> dict:
    """신뢰도 기준값 검증: 기준값 미만으로 표시한 항목에 실제 오류가 얼마나 들어 있는가."""
    low, high = c[("low", "ok")] + c[("low", "err")], c[("high", "ok")] + c[("high", "err")]
    errs = c[("low", "err")] + c[("high", "err")]
    return {
        "threshold": threshold,
        "low_items": low,
        "high_items": high,
        "error_rate_low": ratio(c[("low", "err")], low),
        "error_rate_high": ratio(c[("high", "err")], high),
        "flag_precision": ratio(c[("low", "err")], low),   # 신뢰도 낮음 표시 중 실제 오류 비율
        "flag_recall": ratio(c[("low", "err")], errs),     # 실제 오류 중 신뢰도 낮음으로 잡힌 비율
    }


def _lot_report(lot_conf: dict[str, Counter]) -> dict:
    conf = defaultdict(Counter, lot_conf)  # 아래 조회가 원본에 빈 키를 만들지 않도록 복사본에서 읽는다
    A, H, R = LotRecommendation.APPROVE.value, LotRecommendation.HOLD.value, LotRecommendation.REJECT.value
    total = sum(sum(c.values()) for c in conf.values())
    correct = sum(conf[k][k] for k in conf)
    normal = sum(conf[A].values())
    return {
        "documents": total,
        "accuracy": ratio(correct, total),
        "auto_process_rate": ratio(conf[A][A], normal),       # 정상 자동 처리율
        "over_hold_rate": ratio(conf[A][H], normal),          # 과잉 보류율
        "false_reject_rate": ratio(conf[A][R], normal),       # 정상 문서를 불합격 권고
        "normal_documents": normal,
        "confusion": {g: dict(c) for g, c in lot_conf.items()},
    }
