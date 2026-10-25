"""[담당: 장수민] 대표 데모 20 로트 수용 테스트 (멘토님 범위 정의서 6장, 평가 계획 "업무 시나리오 성공률"). 실제 DB 필요.

사례는 tests/fixtures/demo20_scenarios.json 에 있다. 사례마다 가상 CoA(목업 추출 JSON)를 업로드하고
  - 결과 상태: 로트 권고, 항목 판정
  - 사유코드: 항목 reason_code, 문서 정합성 오류
  - 조치: 보류 후속 조치 추천, 공급사 요청 / 내부 확인 목록, 문의 초안
가 기대값과 모두 맞는지 본다. 아직 구현하지 않은 기능의 사례(pending)는 strict xfail 이라,
구현되면 xfail 이 깨져서 pending 을 지우라고 알려 준다.

결과 한눈에 보기: python -m pytest tests/api/test_demo20_acceptance.py -v
"""
import copy
import json
from pathlib import Path

import pytest

from app.core.config import settings
from seeds.seed_specs import seed_specs

PDF = b"%PDF-1.7\n" + b"0" * 50
SCENARIOS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "demo20_scenarios.json")
                       .read_text(encoding="utf-8"))
CASES = SCENARIOS["cases"]


def build_coa(patch: dict | None, *, lot_no: str | None = None) -> dict:
    """base CoA 에 patch(set: 항목 추가·덮어쓰기, remove: 항목 삭제)를 적용한 목업 추출 JSON."""
    coa = copy.deepcopy(SCENARIOS["base"])
    patch = patch or {}
    rows = {r["normalized_name"]: r for r in coa["items"] if r["normalized_name"] not in patch.get("remove", [])}
    for name, fields in patch.get("set", {}).items():
        rows.setdefault(name, {"normalized_name": name}).update(fields)
    coa["items"] = [
        {"raw_name": r.get("raw_name", r["normalized_name"]), "mapping_source": "dictionary", "confidence": 0.95, **r}
        for r in rows.values()
    ]
    if lot_no:
        coa["lot_no"] = lot_no
    return coa


@pytest.fixture
def upload(auth_client, db, tmp_path, monkeypatch):
    seed_specs(db)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    monkeypatch.setattr(settings, "UNMAPPED_AI_ITEM", "check")   # 로컬 .env 와 무관하게 기본 정책으로

    def _upload(name: str, coa: dict, *, spec_set: str | None = None, received_lot_no: str | None = None) -> str:
        (mock_dir / f"{name}.json").write_text(json.dumps(coa, ensure_ascii=False), encoding="utf-8")
        data = {"material_code": "LI2CO3"}
        if spec_set:
            data["spec_set_code"] = spec_set
        if received_lot_no:
            data["received_lot_no"] = received_lot_no
        r = auth_client.post("/api/v1/documents", files={"file": (f"{name}.pdf", PDF)}, data=data)
        assert r.status_code == 201, r.text
        return r.json()["data"]["document_id"]
    return _upload


def _params():
    for case in CASES:
        marks = [pytest.mark.xfail(reason=case["pending"], strict=True)] if case.get("pending") else []
        yield pytest.param(case, id=f'demo{case["id"]}', marks=marks)


@pytest.mark.parametrize("case", list(_params()))
def test_demo_lot(case, upload, auth_client):
    exp = case["expected"]
    if "repeat_lots" in case:
        _check_anomaly(case, upload, auth_client)
        return

    doc_id = upload(f'demo{case["id"]}', build_coa(case.get("patch")),
                    spec_set=case.get("spec_set"), received_lot_no=case.get("received_lot_no"))
    result = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]
    items = {i["normalized_name"]: i for i in result["items"]}

    # ---- 결과 상태 ----
    assert result["lot_recommendation"] == exp["lot_recommendation"], _why(result)
    for key, n in exp.get("summary", {}).items():
        assert result["summary"][key] == n, result["summary"]
    for name, fields in exp.get("items", {}).items():
        assert name in items, f"{name} 항목 없음: {sorted(items)}"
        for field, value in fields.items():
            actual = items[name][field]
            if isinstance(value, float | int) and not isinstance(value, bool) and actual is not None:
                assert actual == pytest.approx(value, abs=1e-3), (name, field, actual)
            else:
                assert actual == value, (name, field, actual, items[name]["judgement_reason"])

    # ---- 사유코드 (문서 정합성) ----
    assert [i["code"] for i in result["document_issues"]] == exp.get("document_issues", [])

    # ---- 조치 ----
    keys = {"follow_up", "supplier_codes", "internal_codes", "draft_mentions"}
    if keys & exp.keys():
        f = auth_client.get(f"/api/v1/documents/{doc_id}/follow-ups").json()["data"]
        if "follow_up" in exp:
            assert f["suggested_follow_up"] == exp["follow_up"]
        if "supplier_codes" in exp:
            assert sorted({ln["code"] for ln in f["supplier_lines"]}) == sorted(exp["supplier_codes"])
        if "internal_codes" in exp:
            assert sorted({ln["code"] for ln in f["internal_lines"]}) == sorted(exp["internal_codes"])
        for word in exp.get("draft_mentions", []):
            assert f["draft"] and word in f["draft"]["body"], f["draft"]


def _check_anomaly(case, upload, auth_client):
    """데모 20: 여러 로트에 같은 결과가 반복되면 이상 패턴 경고 (위조 판정은 하지 않음)."""
    ids = [upload(f'demo20-{lot}', build_coa(case.get("patch"), lot_no=lot)) for lot in case["repeat_lots"]]
    r = auth_client.get(f"/api/v1/documents/{ids[-1]}/anomalies")
    assert r.status_code == 200, r.status_code
    assert r.json()["data"], "이상 패턴 경고 없음"


def _why(result) -> str:
    return "; ".join(f'{i["normalized_name"]}={i["judgement"]}({i["reason_code"]})'
                     for i in result["items"] if i["judgement"] != "pass") or "모두 적합"


def test_scenario_file_covers_20_lots():
    assert [c["id"] for c in CASES] == [f"{n:02d}" for n in range(1, 21)]
