"""[담당: 장수민] 로트 권고 테스트 — 명세 2.4 표 1행 = 테스트 1개, 이후는 누락 항목 생성과 문서 전체 판정."""
from datetime import date

import pytest

from app.core.enums import Judgement as J, LotRecommendation as L, MappingSource, ReviewStatus
from app.schemas.extraction import ExtractedItem, ExtractionInput, ExtractionItem
from app.services.judgement.engine import judge_document, refresh_summary
from app.services.judgement.lot_recommend import recommend, summarize
from app.services.judgement.missing_items import build_missing_items
from app.services.judgement.spec_rule import SpecRule


def items(*judgements):
    return [
        ExtractionItem(item_id=f"item-{i}", normalized_name=f"x{i}", judgement=j)
        for i, j in enumerate(judgements)
    ]


# ---- 명세 2.4 표 -----------------------------------------------------------
def test_any_fail_reject():
    assert recommend(summarize(items(J.PASS, J.FAIL, J.CHECK))) == L.REJECT


@pytest.mark.parametrize("j", [J.UNDETERMINED, J.MISSING, J.CHECK])
def test_no_fail_but_pending_hold(j):
    assert recommend(summarize(items(J.PASS, j))) == L.HOLD


def test_all_pass_approve():
    assert recommend(summarize(items(J.PASS, J.PASS))) == L.APPROVE


def test_summary_counts():
    s = summarize(items(J.PASS, J.PASS, J.FAIL, J.MISSING, J.CHECK, J.CHECK))
    assert s.model_dump() == {"pass": 2, "fail": 1, "undetermined": 0, "missing": 1, "check": 2}


# ---- 누락 항목 생성 --------------------------------------------------------
SPECS = [
    SpecRule("순도", unit="%", lsl=99.5, usl=None),
    SpecRule("Na", unit="ppm", lsl=None, usl=25),
    SpecRule("Fe", unit="ppm", lsl=None, usl=5),
]


def test_build_missing_items_only_for_absent_specs():
    present = [ExtractedItem(normalized_name="na"), ExtractedItem(normalized_name="순도 ")]
    missing = build_missing_items(present, SPECS)
    assert [m.normalized_name for m in missing] == ["Fe"]
    m = missing[0]
    assert (m.item_id, m.mapping_source, m.raw_name, m.raw_value, m.confidence, m.bbox) == (
        "spec-001", MappingSource.SPEC, None, None, None, None)


# ---- 문서 전체 판정 (engine) -----------------------------------------------
def coa(**over):
    data = dict(
        supplier="Chengxin", lot_no="L-2409-01", test_date=date(2026, 9, 20), applied_standard="YS/T 582-2023 D1",
        items=[
            ExtractedItem(normalized_name="순도", raw_value="99.62", unit="%", confidence=0.97),
            ExtractedItem(normalized_name="Na", raw_value="< 20", unit="ppm", confidence=0.91),
            ExtractedItem(normalized_name="Fe", raw_value="3", unit="ppm", confidence=0.93),
            # 외관은 사전으로 매핑되는 참고 항목 (이 SPECS 에는 규격이 없음)
            ExtractedItem(normalized_name="외관", raw_value="White powder", confidence=0.9,
                          mapping_source=MappingSource.DICTIONARY),
        ],
    )
    data.update(over)
    return ExtractionInput(**data)


def test_judge_document_all_pass_approve():
    r = judge_document(coa(), document_id="doc-1", specs=SPECS, threshold=0.8)
    assert r.lot_recommendation == L.APPROVE
    assert r.summary.model_dump() == {"pass": 4, "fail": 0, "undetermined": 0, "missing": 0, "check": 0}
    assert [i.item_id for i in r.items] == ["item-001", "item-002", "item-003", "item-004"]
    assert r.review_status == ReviewStatus.PENDING
    j = r.to_json()
    assert j["test_date"] == "2026-09-20" and j["summary"]["pass"] == 4 and j["items"][0]["judgement"] == "pass"


def test_judge_document_adds_missing_and_holds():
    c = coa()
    c.items = c.items[:2]  # Fe 빠짐
    r = judge_document(c, document_id="doc-1", specs=SPECS, threshold=0.8)
    assert r.items[-1].judgement == J.MISSING and r.items[-1].item_id == "spec-001"
    assert r.lot_recommendation == L.HOLD


def test_judge_document_keeps_ai_item_ids():
    c = coa()
    c.items[0].item_id = "ai-7"
    r = judge_document(c, document_id="doc-1", specs=SPECS, threshold=0.8)
    assert r.items[0].item_id == "ai-7" and r.items[1].item_id == "item-002"


def test_refresh_summary_after_item_change():
    r = judge_document(coa(), document_id="doc-1", specs=SPECS, threshold=0.8)
    r.items[2] = r.items[2].model_copy(update={"judgement": J.FAIL})
    refresh_summary(r)
    assert r.lot_recommendation == L.REJECT and r.summary.fail == 1
