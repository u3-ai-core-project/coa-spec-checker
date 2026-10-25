"""[담당: 홍채령] 이상 패턴 API (명세 4.17, 확장) — 지금은 identical_values 만"""
import json

import pytest

from app.core.config import settings
from app.core.enums import DocumentStatus, SpecType
from app.models import Document, ExtractionResult, SpecItem, SpecSet

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100


def url(doc_id):
    return f"/api/v1/documents/{doc_id}/anomalies"


def item(name, raw, qualifier="exact", reason_code=None):
    return {"normalized_name": name, "raw_value": raw, "value_qualifier": qualifier, "reason_code": reason_code}


def make_doc(db, user, lot, items, supplier="Chengxin", material="LI2CO3"):
    doc = Document(file_name=f"{lot}.pdf", file_path="x", file_size=1, content_type="application/pdf",
                   material_code=material, supplier=supplier, lot_no=lot,
                   status=DocumentStatus.EXTRACTED, uploaded_by=user.id)
    doc.extraction = ExtractionResult(result={"items": items})
    db.add(doc)
    db.commit()
    return doc


def test_identical_values_with_other_lot(auth_client, db, user):
    a = make_doc(db, user, "A0266047", [item("Ca", "90 ppm"), item("Na", "12 ppm")])
    b = make_doc(db, user, "A0285657", [item("Ca", "90 ppm"), item("Na", "15 ppm")])
    r = auth_client.get(url(b.id))
    assert r.status_code == 200
    assert r.json()["data"] == [{
        "type": "identical_values",
        "item_name": "Ca",
        "message": "다른 로트(A0266047)와 값이 같습니다. Ca 90 ppm",
        "related_document_ids": [a.id],
    }]


def test_compares_reported_text_not_converted_value(auth_client, db, user):
    """'소수점까지 같음': 원문 표기가 같아야 한다. 공백·대소문자만 무시."""
    make_doc(db, user, "L1", [item("Fe", "3.0 PPM"), item("Cl", "10 ppm")])
    b = make_doc(db, user, "L2", [item("Fe", "3.0ppm"), item("Cl", "10.0 ppm")])
    names = [a["item_name"] for a in auth_client.get(url(b.id)).json()["data"]]
    assert names == ["Fe"]


@pytest.mark.parametrize("raw, qualifier, reason", [
    ("< 20 ppm", "less_than", None),                    # 상한값 표기
    ("none detected", "not_detected", None),            # 검출 안 됨
    ("=<1000 ppm", "less_equal", "SPEC_COPIED"),         # 규격 문구 복사
])
def test_non_measured_values_are_ignored(auth_client, db, user, raw, qualifier, reason):
    make_doc(db, user, "L1", [item("K", raw, qualifier, reason)])
    b = make_doc(db, user, "L2", [item("K", raw, qualifier, reason)])
    assert auth_client.get(url(b.id)).json()["data"] == []


def test_other_supplier_same_lot_or_missing_info_ignored(auth_client, db, user):
    make_doc(db, user, "L1", [item("Ca", "90 ppm")], supplier="대흥리튬")       # 다른 협력사
    make_doc(db, user, "L2", [item("Ca", "90 ppm")])                          # 같은 로트 (재업로드)
    make_doc(db, user, "L3", [item("Ca", "90 ppm")], material="LIOH")         # 다른 원자재
    b = make_doc(db, user, "L2", [item("Ca", "90 ppm")], supplier="chengxin ")
    assert auth_client.get(url(b.id)).json()["data"] == []
    no_lot = make_doc(db, user, None, [item("Ca", "90 ppm")])
    assert auth_client.get(url(no_lot.id)).json()["data"] == []


def test_multiple_previous_lots(auth_client, db, user):
    a = make_doc(db, user, "L1", [item("Ca", "90 ppm")])
    b = make_doc(db, user, "L2", [item("Ca", "90 ppm")])
    c = make_doc(db, user, "L3", [item("Ca", "90 ppm")])
    data = auth_client.get(url(c.id)).json()["data"]
    assert data[0]["message"] == "다른 로트(L1, L2)와 값이 같습니다. Ca 90 ppm"
    assert data[0]["related_document_ids"] == [a.id, b.id]


def test_document_without_extraction_is_empty(auth_client, db, user):
    doc = Document(file_name="q.pdf", file_path="x", file_size=1, content_type="application/pdf",
                   material_code="LI2CO3", supplier="Chengxin", status=DocumentStatus.QUEUED, uploaded_by=user.id)
    db.add(doc)
    db.commit()
    assert auth_client.get(url(doc.id)).json()["data"] == []


def test_not_found_and_requires_login(auth_client, client, db):
    r = auth_client.get(url("nope"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
    from app.api.deps import get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get(url("nope")).status_code == 401


def test_end_to_end_with_upload(auth_client, db, tmp_path, monkeypatch):
    """업로드 → 서버 판정(value_qualifier 채움) → 이상 패턴. 로트만 다른 같은 결과 CoA 3건 (데모 20)."""
    spec_set = SpecSet(code="LI2CO3-T", material_code="LI2CO3", material_name="탄산리튬", grade="D1", is_default=True)
    spec_set.items = [SpecItem(item_name="Ca", unit="ppm", usl=20, spec_type=SpecType.QUANTITATIVE)]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    for lot in ("L1", "L2", "L3"):
        mock = {"supplier": "Chengxin", "lot_no": lot,
                "items": [{"raw_name": "Ca", "normalized_name": "Ca", "mapping_source": "dictionary",
                           "raw_value": "15", "unit": "ppm", "confidence": 0.95}]}
        (mock_dir / f"{lot}.json").write_text(json.dumps(mock), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    ids = [auth_client.post("/api/v1/documents", files={"file": (f"{lot}.pdf", PDF)},
                            data={"material_code": "LI2CO3"}).json()["data"]["document_id"] for lot in ("L1", "L2", "L3")]
    data = auth_client.get(url(ids[-1])).json()["data"]
    assert len(data) == 1 and data[0]["item_name"] == "Ca"
    assert data[0]["related_document_ids"] == ids[:2]
