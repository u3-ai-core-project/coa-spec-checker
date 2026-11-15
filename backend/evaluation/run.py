"""[담당: 홍채령] 평가 실행.

    cd backend
    python -m evaluation.run --gt <정답 라벨 폴더> --pred <시스템 출력 폴더> [--baseline <베이스라인 출력 폴더>]

리포트는 --out 폴더(기본 evaluation/reports/<시각>)에 report.json, report.md 로 저장한다.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from evaluation.data import load_ground_truth, load_predictions
from evaluation.report import build_report, to_markdown

# 판정 결과에 영향을 주는 서버 설정. 리포트에 남겨 정책별 결과를 비교할 수 있게 한다.
POLICY_KEYS = ("LOW_CONFIDENCE_THRESHOLD", "REASON_JUDGEMENT", "ND_LIMIT_INCLUSIVE", "UNMAPPED_AI_ITEM", "CROSS_RULES")


def current_policy() -> dict:
    """이 컴퓨터의 .env 기준 판정 정책. 시스템 출력을 만든 서버와 설정이 같다는 전제다 (다르면 --policy 로 지정)."""
    from app.core.config import settings
    return {k: getattr(settings, k) for k in POLICY_KEYS}


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description="CoA 추출·판정 평가")
    ap.add_argument("--gt", type=Path, required=True, help="정답 라벨 JSON 폴더 (또는 파일 1개)")
    ap.add_argument("--pred", type=Path, required=True, help="시스템 출력 JSON 폴더 (GET /extraction 응답 또는 ExtractionInput)")
    ap.add_argument("--baseline", type=Path, help="규칙 베이스라인 출력 JSON 폴더 (시스템 출력과 같은 형식)")
    ap.add_argument("--out", type=Path, help="리포트 저장 폴더 (기본: evaluation/reports/<시각>)")
    ap.add_argument("--threshold", type=float, help="신뢰도 기준값 (기본: 서버 설정 LOW_CONFIDENCE_THRESHOLD)")
    ap.add_argument("--policy", type=Path, help="시스템 출력을 만든 서버의 판정 정책 JSON (기본: 현재 .env 설정)")
    args = ap.parse_args(argv)

    policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else current_policy()
    threshold = args.threshold if args.threshold is not None else float(policy.get("LOW_CONFIDENCE_THRESHOLD", 0.8))

    gt = load_ground_truth(args.gt)
    preds = load_predictions(args.pred)
    baseline = load_predictions(args.baseline) if args.baseline else None

    report = build_report(gt, preds, baseline, threshold, meta={
        "gt": str(args.gt), "pred": str(args.pred), "baseline": str(args.baseline) if args.baseline else None,
        "policy": policy,
    })

    out = args.out or Path(__file__).parent / "reports" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(report), encoding="utf-8")
    print(f"리포트 저장: {out / 'report.md'}")
    return out


if __name__ == "__main__":
    main()
