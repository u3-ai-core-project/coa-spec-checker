"""[담당: 홍채령] 대표 데모 20 로트 결과표 (회의 6차 안건 13, 14).

    cd backend
    python -m evaluation.demo20 [--out <폴더>]

수용 테스트(tests/api/test_demo20_acceptance.py, 담당: 장수민)를 돌려 사례별 통과 여부를 모으고, 같은 사례를 판정 엔진에
넣어 사람에게 넘어가는 항목 수를 센다. 리포트는 --out 폴더(기본 evaluation/reports/demo20)에 report.json, report.md 로 저장한다.
수용 테스트에 실제 DB(coa_test)가 필요하다.

사람이 실제로 확인한 항목 수·처리 시간과 엑셀 대조 시간(안건 14)은 사람이 측정해야 하는 값이라 여기서 만들지 않는다.
"""
import argparse
import csv
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from app.core.config import settings
from app.core.enums import Judgement, SpecType
from app.schemas.extraction import DocumentIssue, ExtractionInput
from app.services.judgement.engine import judge_document
from app.services.judgement.spec_rule import SpecRule
from tests.api.test_demo20_acceptance import CASES, build_coa

BACKEND = Path(__file__).resolve().parents[1]
SEED_ITEMS = BACKEND / "seeds" / "data" / "spec_items_li2co3.csv"
TEST_FILE = "tests/api/test_demo20_acceptance.py"
DEFAULT_SET = "LI2CO3-D1-2023"
RECOMMENDATION_KO = {"approve": "승인", "hold": "보류", "reject": "불합격"}


def load_rules(spec_set: str) -> list[SpecRule]:
    with SEED_ITEMS.open(encoding="utf-8") as f:
        return [
            SpecRule(
                r["item_name"], r["unit"] or None,
                float(r["lsl"]) if r["lsl"] else None, float(r["usl"]) if r["usl"] else None,
                SpecType(r["spec_type"]), r["is_required"] == "true",
            )
            for r in csv.DictReader(f) if r["spec_set_code"] == spec_set
        ]


def judge_case(case: dict) -> dict:
    """사례 1건의 로트 권고와 항목 수. 문서 정합성 오류는 입고 정보가 있어야 나오므로 수용 테스트의 기대값을 넘긴다."""
    issues = [DocumentIssue(code=code, message=code) for code in case["expected"].get("document_issues", [])]
    result = judge_document(
        ExtractionInput.model_validate(build_coa(case.get("patch"))),
        document_id=f'demo{case["id"]}', specs=load_rules(case.get("spec_set", DEFAULT_SET)), issues=issues,
    )
    judged = [i for i in result.items if i.judgement is not None]
    flagged = [i.normalized_name for i in judged if i.judgement != Judgement.PASS]
    return {
        "lot_recommendation": str(result.lot_recommendation),
        "item_count": len(judged),
        "flagged_items": flagged,
        "document_issues": [str(i.code) for i in issues],
    }


def run_acceptance_tests() -> dict[str, str]:
    """{사례 id: passed | failed | xfailed | skipped}"""
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        subprocess.run([sys.executable, "-m", "pytest", TEST_FILE, "-q", f"--junitxml={xml}"],
                       cwd=BACKEND, capture_output=True, check=False)
        if not xml.exists():
            raise SystemExit("수용 테스트를 실행하지 못했습니다. DB(docker compose up -d)를 확인해 주세요.")
        outcomes = {}
        for case in ET.parse(xml).getroot().iter("testcase"):
            name = case.get("name", "")
            if "[demo" not in name:
                continue
            skipped = case.find("skipped")
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif skipped is None:
                outcome = "passed"
            else:
                outcome = "xfailed" if skipped.get("type") == "pytest.xfail" else "skipped"
            outcomes[name.split("[demo")[1].rstrip("]")] = outcome
        return outcomes


def build_report(outcomes: dict[str, str]) -> dict:
    rows = [{"id": c["id"], "title": c["title"], "mentor": c["mentor"], "outcome": outcomes.get(c["id"], "not_run"),
             **judge_case(c)} for c in CASES]
    items = sum(r["item_count"] for r in rows)
    flagged = sum(len(r["flagged_items"]) for r in rows)
    lots = {key: sum(r["lot_recommendation"] == key for r in rows) for key in RECOMMENDATION_KO}
    return {
        "rows": rows,
        "passed": sum(r["outcome"] == "passed" for r in rows),
        "total": len(rows),
        "lots": lots,
        "item_count": items,
        "flagged_item_count": flagged,
        "unmapped_ai_item": settings.UNMAPPED_AI_ITEM,
    }


def to_markdown(report: dict) -> str:
    lots, items, flagged = report["lots"], report["item_count"], report["flagged_item_count"]
    lines = [
        "# 대표 데모 20 로트 결과",
        "",
        f'- 수용 테스트 통과: **{report["passed"]} / {report["total"]}** (로트 권고, 항목 판정, 사유코드, 조치 기대값이 모두 일치)',
        f'- 로트 권고: 승인 {lots["approve"]}, 보류 {lots["hold"]}, 불합격 {lots["reject"]}',
        f"- 사람에게 넘어가는 항목: {flagged} / {items} ({flagged / items * 100:.1f}%)" if items else "- 항목 없음",
        "",
        "입력은 가상 추출 결과(tests/fixtures/demo20_scenarios.json)입니다. 실제 PDF 추출은 포함하지 않습니다.",
        "데모 20 로트는 예외 사례 위주로 고른 세트라, 위 비율을 실제 운영의 자동 처리율로 해석하면 안 됩니다.",
        "",
        "| 사례 | 상황 | 멘토님 기대 | 결과 | 로트 권고 | 사람 확인 항목 | 문서 정합성 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in report["rows"]:
        flagged_names = ", ".join(r["flagged_items"]) or "-"
        issues = ", ".join(r["document_issues"]) or "-"
        lines.append(f'| {r["id"]} | {r["title"]} | {r["mentor"]} | {r["outcome"]} | '
                     f'{RECOMMENDATION_KO.get(r["lot_recommendation"], "-")} | {flagged_names} | {issues} |')
    lines += [
        "",
        "## 사람 개입 비교 (안건 14)",
        "",
        "| 값 | 상태 |",
        "| --- | --- |",
        f"| 시스템이 사람에게 넘기는 항목 수 | {flagged} / {items} |",
        "| 사람이 실제로 확인한 항목 수 (reviewed) | 미측정. 검수 화면에서 20 로트를 처리한 뒤 기록 |",
        "| 보조형 처리 시간 | 미측정. 위와 같은 실행의 업로드~처분 시간 |",
        "| 수동(엑셀 대조) 처리 시간 | 미측정. 같은 로트를 사람이 대조하며 측정 |",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "reports" / "demo20", help="리포트 저장 폴더")
    args = ap.parse_args(argv)
    report = build_report(run_acceptance_tests())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "report.md").write_text(to_markdown(report), encoding="utf-8")
    print(f"리포트 저장: {args.out / 'report.md'}")
    return args.out


if __name__ == "__main__":
    main()
