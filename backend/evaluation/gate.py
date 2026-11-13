"""[담당: 장수민] 모델 갱신 평가 통과 점검 (운영 정책 7장).

모델, 프롬프트, 신뢰도 상한, 매핑 사전을 바꾸면 평가를 다시 돌려(python -m evaluation.run), 아래를 모두 지킬 때만 반영한다.

  1. 부적합 항목을 적합으로 잘못 판정한 건수 0건, 잘못된 승인 권고 0건
  2. 문의 초안에 지어낸 숫자 0건
  3. 항목 인식률과 수치 일치율이 직전보다 1%p 넘게 떨어지지 않을 것
  4. 평가용 자료와 규칙 보강용 자료를 나눌 것

    cd backend
    python -m evaluation.gate --new <새 리포트 폴더> --previous <직전 리포트 폴더> \\
        --invented-numbers <문의 초안 평가에서 센 건수> --tuning-gt <규칙 보강에 쓴 정답 폴더>

확인하지 못한 항목(--invented-numbers, --tuning-gt 를 안 준 경우)은 통과로 보지 않는다.
모두 통과하면 종료 코드 0, 하나라도 못 지키면 1.
"""
import argparse
import json
import sys
from pathlib import Path

MAX_DROP = 0.01  # 1%p. 리포트의 비율은 0~1 이다


def _load(folder: Path) -> dict:
    return json.loads((folder / "report.json").read_text(encoding="utf-8"))


def _overall(report: dict) -> dict:
    return report["system"]["overall"] if "system" in report else report["overall"]


def _stems(folder: Path) -> set[str]:
    return {p.stem for p in (folder.glob("*.json") if folder.is_dir() else [folder])}


def false_approvals(overall: dict) -> int:
    """정답은 불합격·보류인데 승인 권고로 나간 문서 수 (잘못된 승인 권고)."""
    confusion = overall["lot"]["confusion"]
    return sum(c.get("approve", 0) for truth, c in confusion.items() if truth != "approve")


def check(new: dict, previous: dict, *, invented_numbers: int | None, eval_stems: set[str] | None,
          tuning_stems: set[str] | None) -> list[tuple[str, bool | None, str]]:
    """[(기준, 통과 여부(None=확인 못 함), 설명)]"""
    n, p = _overall(new), _overall(previous)
    results: list[tuple[str, bool | None, str]] = []

    hidden = n["judgement"]["hidden_fail_missed"]
    results.append(("부적합 → 적합 0건", hidden == 0, f"{hidden}건"))
    wrong = false_approvals(n)
    results.append(("잘못된 승인 권고 0건", wrong == 0, f"{wrong}건"))

    if invented_numbers is None:
        results.append(("문의 초안 지어낸 숫자 0건", None, "건수를 주지 않아 확인하지 못함 (--invented-numbers)"))
    else:
        results.append(("문의 초안 지어낸 숫자 0건", invented_numbers == 0, f"{invented_numbers}건"))

    for key, label in (("item_recall", "항목 인식률"), ("value_accuracy", "수치 일치율")):
        now, before = n["extraction"][key], p["extraction"][key]
        if now is None or before is None:
            results.append((f"{label} 하락 1%p 이내", None, "비교할 값이 없음"))
        else:
            drop = round(before - now, 4)
            results.append((f"{label} 하락 1%p 이내", drop <= MAX_DROP,
                            f"직전 {before * 100:.1f}% → 이번 {now * 100:.1f}% ({-drop * 100:+.1f}%p)"))

    if tuning_stems is None or eval_stems is None:
        why = "보강에 쓴 자료를 주지 않아" if tuning_stems is None else "리포트에 적힌 평가용 정답 폴더를 찾지 못해"
        results.append(("평가용·보강용 자료 분리", None, f"{why} 확인하지 못함 (--tuning-gt)"))
    else:
        shared = sorted(eval_stems & tuning_stems)
        results.append(("평가용·보강용 자료 분리", not shared,
                        "겹치는 문서 없음" if not shared else f"겹치는 문서 {len(shared)}건: {', '.join(shared[:5])}"))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="모델 갱신 평가 통과 점검")
    ap.add_argument("--new", type=Path, required=True, help="이번 평가 리포트 폴더 (report.json)")
    ap.add_argument("--previous", type=Path, required=True, help="직전에 반영한 평가 리포트 폴더")
    ap.add_argument("--invented-numbers", type=int, help="문의 초안 평가에서 센, 지어낸 숫자 건수")
    ap.add_argument("--tuning-gt", type=Path, help="규칙 보강에 쓴 정답 폴더 (평가용 정답 폴더와 겹치면 안 됨)")
    args = ap.parse_args(argv)

    new = _load(args.new)
    eval_gt = Path(new.get("meta", {}).get("gt", ""))
    eval_stems = _stems(eval_gt) if str(eval_gt) and eval_gt.exists() else None
    tuning = _stems(args.tuning_gt) if args.tuning_gt else None
    results = check(new, _load(args.previous), invented_numbers=args.invented_numbers,
                    eval_stems=eval_stems, tuning_stems=tuning)

    for name, ok, note in results:
        mark = "통과" if ok else ("확인 못 함" if ok is None else "실패")
        print(f"[{mark}] {name}: {note}")
    passed = all(ok for _, ok, _ in results)
    print("\n결과:", "모두 지켰습니다. 반영해도 됩니다." if passed else "반영하지 않습니다.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
