"""[담당: 장수민] 복수 로트 문서 테스트 (운영 정책 8.1). 실제 DB 필요.

한 파일에서 로트가 2개 이상 읽히면 첫 로트만 채택하지 않고, 복수 로트 문서로 표시해 담당자 확인(보류 권고)으로 넘긴다.
"""
import json

import pytest

from app.core.config import settings
from app.core.enums import SpecType
from app.models import SpecItem, SpecSet

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


@pytest.fixture
def upload(auth_client, db, tmp_path, monkeypatch):
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))

    def _upload(name: str, *, lot_no=None, lot_nos=None, received_lot_no=None) -> str:
        data = {"items": [{"raw_name": "Na", "normalized_name": "Na", "mapping_source": "dictionary",
                           "raw_value": "12", "unit": "ppm", "confidence": 0.95}]}
        if lot_no:
            data["lot_no"] = lot_no
        if lot_nos:
            data["lot_nos"] = lot_nos
        (mock_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        form = {"material_code": "LI2CO3"}
        if received_lot_no:
            form["received_lot_no"] = received_lot_no
        r = auth_client.post("/api/v1/documents", files={"file": (f"{name}.pdf", PDF)}, data=form)
        assert r.status_code == 201, r.text
        return r.json()["data"]["document_id"]
    return _upload


def get(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_multi_lot_document_goes_to_manual_check(auth_client, upload):
    doc_id = upload("fisher", lot_no="L-1", lot_nos=["L-1", "L-2", "L-3"])
    detail = get(auth_client, f"/api/v1/documents/{doc_id}")
    assert detail["is_multi_lot"] is True
    assert detail["lot_no"] is None                                     # 첫 로트만 채택하지 않는다
    assert detail["lot_nos"] == ["L-1", "L-2", "L-3"]
    assert detail["lot_recommendation"] == "hold"                       # 항목이 모두 적합이어도 보류 권고
    result = get(auth_client, f"/api/v1/documents/{doc_id}/extraction")
    assert [i["code"] for i in result["document_issues"]] == ["MULTI_LOT"]
    assert result["lot_nos"] == ["L-1", "L-2", "L-3"]


def test_single_lot_document_is_unchanged(auth_client, upload):
    doc_id = upload("single", lot_no="L-1", lot_nos=["l1"])             # 같은 로트를 다르게 쓴 것은 복수 로트가 아니다
    detail = get(auth_client, f"/api/v1/documents/{doc_id}")
    assert (detail["is_multi_lot"], detail["lot_no"], detail["lot_nos"]) == (False, "L-1", [])
    assert detail["lot_recommendation"] == "approve"


def test_multi_lot_with_wrong_received_lot_also_mismatches(auth_client, upload):
    doc_id = upload("fisher", lot_nos=["L-1", "L-2"], received_lot_no="L-9")
    result = get(auth_client, f"/api/v1/documents/{doc_id}/extraction")
    assert [i["code"] for i in result["document_issues"]] == ["MULTI_LOT", "LOT_MISMATCH"]


def test_multi_lot_with_matching_received_lot_only_flags_multi_lot(auth_client, upload):
    doc_id = upload("fisher", lot_nos=["L-1", "L-2"], received_lot_no="l-2")
    result = get(auth_client, f"/api/v1/documents/{doc_id}/extraction")
    assert [i["code"] for i in result["document_issues"]] == ["MULTI_LOT"]


def test_multi_lot_document_is_not_grouped_as_reissue(auth_client, upload):
    first = upload("a", lot_no="L-1")
    upload("b", lot_nos=["L-1", "L-2"])                                  # lot_no 가 비어 있어 L-1 의 재발행으로 묶이지 않는다
    assert get(auth_client, f"/api/v1/reissue/{first}")["status"] == "none"
