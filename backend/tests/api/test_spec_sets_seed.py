"""[담당: 장수민] 탄산리튬 규격 세트 시드 테스트 (10.25, 멘토님 범위 정의서 UC05·데모 03·04). 실제 DB 필요.

저장소의 실제 시드 CSV(seeds/data)를 적재해서 확인한다.
  - LI2CO3-D1-2023     기본 세트 (시연용 규격)
  - LI2CO3-DEMO-R      실물 CoA 판정용 (Mg·자성이물은 별도 성적서 항목이라 필수 아님)
  - LI2CO3-D3-2023     등급 교차 판정 (D1 과 같은 항목을 필수로, D3 한도)
  - LI2CO3-2013        버전 비교용 구판
  - LI2CO3-GENV2-EVAL  가상 CoA 생성기 v2 평가 전용
  - LI2CO3-D1-RELAXED  D1 복사 후 한도 완화 (검수 화면 규격 비교 시연용, 멘토 피드백)
  - LI2CO3-D1-STRICT   D1 복사 후 한도 강화 (같은 용도)
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import SpecItem, SpecSet
from app.services import spec_service
from seeds.seed_specs import seed_specs

PDF = b"%PDF-1.7\n" + b"0" * 50
NEW_SETS = ["LI2CO3-DEMO-R", "LI2CO3-D3-2023", "LI2CO3-2013", "LI2CO3-GENV2-EVAL", "LI2CO3-D1-RELAXED", "LI2CO3-D1-STRICT"]
VOCAB = Path(__file__).resolve().parents[3] / "ai" / "coa_ai" / "vocab.json"


def row(name, raw_value, unit="ppm"):
    return {"raw_name": name, "normalized_name": name, "mapping_source": "dictionary",
            "raw_value": raw_value, "unit": unit, "confidence": 0.95}


# 실제 CoA 아님. D1 필수 항목(순도, Na, K, Fe, Ca, Mg, Pb, 염화물, 황산염, 자성이물)을 모두 갖추고 Na 만 80 ppm
FULL_NA80 = {"supplier": "알파 리튬", "lot_no": "L-080", "items": [
    row("순도", "99.7", "%"), row("Na", "80"), row("K", "5"), row("Fe", "2"), row("Ca", "10"), row("Mg", "5"),
    row("Pb", "1"), row("염화물", "10"), row("황산염", "300"), row("자성이물", "20", "ppb"),
]}
# Fisher 시약급 CoA 처럼 Mg·자성이물이 없고, Pb 대신 중금속 총량만 있는 문서
FISHER_LIKE = {"supplier": "Fisher", "lot_no": "A0396981", "items": [
    row("순도", "99.6", "%"), row("Na", "30"), row("K", "5"), row("Fe", "2"), row("Ca", "10"),
    row("염화물", "10"), row("황산염", "200"), row("중금속 총량", "2"),
]}


@pytest.fixture
def seeded(db):
    seed_specs(db)
    db.commit()


@pytest.fixture
def upload(auth_client, seeded, tmp_path, monkeypatch):
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    for name, data in {"full": FULL_NA80, "fisher": FISHER_LIKE}.items():
        (mock_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _upload(kind: str, spec_set_code: str | None = None) -> dict:
        data = {"material_code": "LI2CO3"}
        if spec_set_code:
            data["spec_set_code"] = spec_set_code
        r = auth_client.post("/api/v1/documents", files={"file": (f"{kind}.pdf", PDF)}, data=data)
        assert r.status_code == 201, r.text
        doc_id = r.json()["data"]["document_id"]
        return auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]
    return _upload


def by_name(result) -> dict:
    return {i["normalized_name"]: i for i in result["items"]}


# ---- 적재 -------------------------------------------------------------------
def test_new_sets_loaded_and_d1_stays_default(db, seeded):
    sets = {s.code: s for s in db.scalars(select(SpecSet))}
    assert set(NEW_SETS) <= set(sets)
    defaults = [code for code, s in sets.items() if s.material_code == "LI2CO3" and s.is_default]
    assert defaults == ["LI2CO3-D1-2023"]                         # 기본 세트는 D1 하나
    assert spec_service.get_default_set(db, "LI2CO3").code == "LI2CO3-D1-2023"


def test_grade_sets_require_same_items_as_d1(db, seeded):
    """D3·2013 은 D1 과 같은 항목을 필수로 둔다 (같은 항목끼리 등급·버전 비교)."""
    def required(code):
        return {i.item_name for i in db.scalars(select(SpecItem).join(SpecItem.spec_set).where(SpecSet.code == code))
                if i.is_required}
    d1 = required("LI2CO3-D1-2023")
    assert required("LI2CO3-D3-2023") == d1 and required("LI2CO3-2013") == d1
    assert required("LI2CO3-DEMO-R") == d1 - {"Mg", "자성이물"}   # 별도 성적서 항목
    assert required("LI2CO3-D1-RELAXED") == d1 and required("LI2CO3-D1-STRICT") == d1


# ---- D1 완화·엄격 (검수 화면 규격 비교용) ----------------------------------------
# 순도는 하한, 나머지는 상한. 순서: 순도, Na, K, Fe, Ca, Mg, Pb, 염화물, 황산염, 자성이물
D1_NAMES = ["순도", "Na", "K", "Fe", "Ca", "Mg", "Pb", "염화물", "황산염", "자성이물"]
RELAXED_LIMITS = [99.5, 100, 20, 10, 40, 20, 3, 30, 600, 100]
STRICT_LIMITS = [99.7, 30, 8, 3, 15, 8, 2, 15, 300, 30]


def limits_of(db, code):
    items = {i.item_name: i for i in db.scalars(select(SpecItem).join(SpecItem.spec_set).where(SpecSet.code == code))}
    return items


@pytest.mark.parametrize("code,grade,expected", [
    ("LI2CO3-D1-RELAXED", "D1-완화", RELAXED_LIMITS),
    ("LI2CO3-D1-STRICT", "D1-엄격", STRICT_LIMITS),
])
def test_d1_variant_sets_limits(db, seeded, code, grade, expected):
    spec_set = db.scalar(select(SpecSet).where(SpecSet.code == code))
    assert (spec_set.grade, spec_set.is_default, spec_set.material_code) == (grade, False, "LI2CO3")
    items = limits_of(db, code)
    assert len(items) == 12                                       # 필수 10 + 중금속 총량 + 외관
    for name, limit in zip(D1_NAMES, expected):
        item = items[name]
        assert (item.lsl, item.usl) == ((limit, None) if name == "순도" else (None, limit)), name
    assert items["자성이물"].unit == "ppb" and items["순도"].unit == "%"
    heavy, appearance = items["중금속 총량"], items["외관"]       # D1 처럼 선택 항목
    assert (heavy.lsl, heavy.usl, heavy.is_required) == (None, None, False)
    assert (appearance.spec_type, appearance.is_required) == ("정성", False)


def test_d1_variants_keep_d1_units_and_names(db, seeded):
    d1 = {n: i.unit for n, i in limits_of(db, "LI2CO3-D1-2023").items()}
    for code in ("LI2CO3-D1-RELAXED", "LI2CO3-D1-STRICT"):
        assert {n: i.unit for n, i in limits_of(db, code).items()} == d1


def test_seed_is_idempotent(db, seeded):
    assert seed_specs(db) == (0, 0)


def test_seeded_item_names_are_ai_standard_names(db, seeded):
    """시드 항목명은 AI 추출기 표준 항목명(normalized_name)과 같아야 판정된다 (ai/coa_ai/vocab.json)."""
    if not VOCAB.exists():
        pytest.skip("ai/coa_ai/vocab.json 없음")
    names = {v["name"] for v in json.loads(VOCAB.read_text(encoding="utf-8"))["items"].values()}
    seeded_names = set(db.scalars(select(SpecItem.item_name).distinct()))
    assert seeded_names - names == set()


# ---- 판정 (멘토님 데모 03·04, DEMO-R) ---------------------------------------
def test_na80_fails_on_d1_passes_on_d3(upload):
    """데모 03·04: Na 80 ppm 은 D1(≤ 50) 부적합, D3(≤ 250) 적합."""
    d1 = upload("full")                                   # 기본 세트
    d3 = upload("full", "LI2CO3-D3-2023")
    assert (by_name(d1)["Na"]["judgement"], d1["lot_recommendation"]) == ("fail", "reject")
    assert (by_name(d3)["Na"]["judgement"], d3["lot_recommendation"]) == ("pass", "approve")
    assert d3["summary"]["missing"] == 0                  # D3 의 선택 항목(Cu, 수분 등)은 없어도 누락 아님


def test_fisher_like_coa_auto_approved_on_demo_r(upload):
    """Mg·자성이물이 없는 실물형 CoA: D1 이면 누락으로 보류, DEMO-R 이면 자동 승인 권고."""
    d1 = upload("fisher")
    demo = upload("fisher", "LI2CO3-DEMO-R")
    assert {n for n, i in by_name(d1).items() if i["judgement"] == "missing"} == {"Mg", "자성이물"}
    assert d1["lot_recommendation"] == "hold"
    assert demo["lot_recommendation"] == "approve" and demo["summary"]["missing"] == 0
    assert by_name(demo)["Pb"]["judgement"] == "pass"     # 중금속 총량 2 ≤ Pb 상한 3 (교차 규칙)


def test_na80_on_relaxed_and_strict(upload):
    """Na 80 ppm: 완화(≤ 100)는 적합, 엄격(≤ 30)은 부적합. D1(≤ 50)과 같은 문서로 비교된다."""
    relaxed = upload("full", "LI2CO3-D1-RELAXED")
    strict = upload("full", "LI2CO3-D1-STRICT")
    assert (by_name(relaxed)["Na"]["judgement"], relaxed["lot_recommendation"]) == ("pass", "approve")
    assert (by_name(strict)["Na"]["judgement"], strict["lot_recommendation"]) == ("fail", "reject")
    # 엄격 기준에서도 Na 말고는 경계 안: K 5(≤ 8), Ca 10(≤ 15), 염화물 10(≤ 15), 황산염 300(≤ 300, 경계값), 순도 99.7(≥ 99.7)
    assert {n for n, i in by_name(strict).items() if i["judgement"] == "fail"} == {"Na"}


def test_genv2_eval_set_limits(upload):
    """생성기 v2 평가용 세트: Na 상한 200 ppm 이라 Na 80 은 적합. 대신 필수 항목이 달라 누락이 생긴다."""
    r = upload("full", "LI2CO3-GENV2-EVAL")
    items = by_name(r)
    assert items["Na"]["judgement"] == "pass"
    assert {n for n, i in items.items() if i["judgement"] == "missing"} == {"Cu", "Mn", "Si", "수분", "입도 D50", "외관"}


# ---- 중금속 총량 → Cu (10.25 회의 결정 6, 홍채령 님 요청) ---------------------------
def genv2_coa_with_heavy_metals() -> dict:
    """생성기 v2 AMBIGUOUS_ANALYTE 사례처럼 Cu 줄 대신 Heavy metals (as Pb) 가 있는 CoA. 나머지 필수 항목은 기준 안."""
    rows = [row("순도", "99.7", "%"), row("Na", "80"), row("K", "5"), row("Ca", "10"), row("Mg", "5"), row("Fe", "2"),
            row("Mn", "1"), row("Si", "10"), row("황산염", "300"), row("염화물", "10"), row("수분", "0.1", "%"),
            row("자성이물", "20", "ppb"), row("입도 D50", "6", "μm"), row("외관", "White powder", None),
            {**row("중금속 총량", "0.8"), "raw_name": "Heavy metals (as Pb)"}]
    return {"supplier": "생성기 v2", "lot_no": "G-001", "items": rows}


def test_genv2_cu_is_ambiguous_with_heavy_metal_total(auth_client, seeded, tmp_path, monkeypatch):
    """GENV2-EVAL: Cu 가 필수인데 중금속 총량만 있으면 누락이 아니라 확인 필요(AMBIGUOUS_ANALYTE, 개별값 요청)."""
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "genv2.json").write_text(json.dumps(genv2_coa_with_heavy_metals(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    r = auth_client.post("/api/v1/documents", files={"file": ("genv2.pdf", PDF)},
                         data={"material_code": "LI2CO3", "spec_set_code": "LI2CO3-GENV2-EVAL"})
    doc_id = r.json()["data"]["document_id"]
    result = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]
    items = by_name(result)
    assert (items["Cu"]["judgement"], items["Cu"]["reason_code"]) == ("check", "AMBIGUOUS_ANALYTE")
    assert [n for n, i in items.items() if i["judgement"] not in ("pass",)] == ["Cu"]
    assert result["lot_recommendation"] == "hold"
    f = auth_client.get(f"/api/v1/documents/{doc_id}/follow-ups").json()["data"]
    assert f["suggested_follow_up"] == "request_single_value"


def test_pb_sets_unchanged_with_heavy_metal_total(upload):
    """Pb 만 있는 기존 세트(D1, DEMO-R)는 이전과 같다: 총량 2 ≤ Pb 상한 3 이면 Pb 적합."""
    d1, demo = upload("fisher"), upload("fisher", "LI2CO3-DEMO-R")
    assert (by_name(d1)["Pb"]["judgement"], by_name(d1)["Pb"]["reason_code"]) == ("pass", None)
    assert (by_name(demo)["Pb"]["judgement"], demo["lot_recommendation"]) == ("pass", "approve")
    assert "Cu" not in by_name(d1) and "Cu" not in by_name(demo)



# ---- 수산화리튬 시드 (10.25 회의 결정, 소성훈 님 LIOH 규격 사전) -------------------
def test_lioh_set_loaded_as_material_default(db, seeded):
    lioh = spec_service.get_default_set(db, "LIOH")
    assert lioh.code == "LIOH-BG-V1" and lioh.version == "SYD-QS-LHM-BG v1"
    items = {i.item_name: i for i in spec_service.get_specs(db, lioh.id)}
    assert len(items) == 15 and all(i.is_required for i in items.values())
    assert (items["LiOH 함량"].lsl, items["LiOH 함량"].usl) == (56.5, 57.5)
    assert (items["Na"].usl, items["Cu"].usl, items["자성이물"].usl) == (30, 1, 50)
    assert (items["입도 D50"].lsl, items["입도 D50"].usl) == (5, 15)
    assert items["외관"].spec_type == "정성"
    assert "B" not in items and "Ni" not in items               # 사내 규격 없는 항목은 참고용이라 넣지 않는다


def test_lioh_does_not_change_li2co3_default(db, seeded):
    assert spec_service.get_default_set(db, "LI2CO3").code == "LI2CO3-D1-2023"
