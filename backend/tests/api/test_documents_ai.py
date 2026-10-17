"""[담당: 고도영] EXTRACTOR=ai 로 업로드부터 판정까지 (실제 DB 와 ai/ 패키지가 필요하다)."""
from pathlib import Path

import pytest

pytest.importorskip("coa_ai")

from app.core.config import settings  # noqa: E402
from app.core.enums import SpecType  # noqa: E402
from app.models import Document, SpecItem  # noqa: E402

FIXTURES = Path(__file__).parents[3] / "ai" / "tests" / "fixtures"
Q, QL = SpecType.QUANTITATIVE, SpecType.QUALITATIVE


@pytest.fixture
def lioh_specs(db):
    """수산화리튬 가상 사내 규격 일부 (소성훈 님 규격 DB 값). 테스트용이며 실제 시드가 아니다."""
    rows = [
        SpecItem(material_code="LIOH", material_name="수산화리튬", item_name=name, unit=unit, lsl=lsl, usl=usl,
                 spec_type=kind, grade="D1", source="test")
        for name, unit, lsl, usl, kind in [
            ("외관", None, None, None, QL),
            ("LiOH 함량", "%", 56.5, 57.5, Q),
            ("탄산", "%", None, 0.35, Q),
            ("Na", "ppm", None, 30, Q),
            ("Ca", "ppm", None, 15, Q),
            ("자성이물", "ppb", None, 50, Q),
            ("입도 D50", "μm", 5.0, 15.0, Q),
        ]
    ]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture
def ai_mode(monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTOR", "ai")


def upload(client, path: Path, name: str | None = None):
    return client.post(
        "/api/v1/documents",
        files={"file": (name or path.name, path.read_bytes(), "application/octet-stream")},
        data={"material_code": "LIOH"},
    )


def test_upload_synthetic_coa_is_extracted_and_judged(auth_client, lioh_specs, ai_mode, db):
    r = upload(auth_client, FIXTURES / "COA_A_0007.pdf")
    assert r.status_code == 201
    doc = db.get(Document, r.json()["data"]["document_id"])
    db.refresh(doc)
    assert doc.status == "extracted", doc.error_message
    assert (doc.lot_no, doc.supplier) == ("SL25-0008", "Selmora Lithium S.A.")

    by_name = {i["normalized_name"]: i for i in doc.extraction.result["items"]}
    assert by_name["탄산"]["judgement"] == "fail"           # 0.36 % > 사내 0.35 % (숨은 불합격)
    assert by_name["탄산"]["deviation"] == pytest.approx(0.01)
    assert by_name["LiOH 함량"]["judgement"] == "pass"
    assert by_name["Na"]["judgement"] == "pass"
    assert by_name["입도 D50"]["judgement"] == "pass"
    assert by_name["외관"]["judgement_reason"] == "정성 항목, 판정 제외"
    assert by_name["Na"]["bbox"]["page"] == 1
    assert doc.lot_recommendation == "reject"


def test_upload_image_fails_with_reason(auth_client, lioh_specs, ai_mode, db, tmp_path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    r = upload(auth_client, image)
    doc = db.get(Document, r.json()["data"]["document_id"])
    db.refresh(doc)
    assert doc.status == "failed"
    assert doc.error_message.startswith("이미지·스캔본 추출은 아직 지원하지 않습니다")
