"""[담당: 고도영] EXTRACTOR=ai 로 업로드부터 판정까지 (실제 DB 와 ai/ 패키지가 필요하다)."""
from pathlib import Path

import pytest

pytest.importorskip("coa_ai")

from app.core.config import settings  # noqa: E402
from app.core.enums import SpecType  # noqa: E402
from app.models import Document, SpecItem, SpecSet  # noqa: E402
from app.schemas.extraction import ExtractionResult  # noqa: E402

FIXTURES = Path(__file__).parents[3] / "ai" / "tests" / "fixtures"
Q, QL = SpecType.QUANTITATIVE, SpecType.QUALITATIVE


@pytest.fixture
def lioh_specs(db):
    """수산화리튬 가상 사내 규격 일부 (소성훈 님 규격 DB 값). 테스트용이며 실제 시드가 아니다."""
    spec_set = SpecSet(code="LIOH-T", material_code="LIOH", material_name="수산화리튬", grade="D1",
                       source="test", is_default=True)
    spec_set.items = [
        SpecItem(item_name=name, unit=unit, lsl=lsl, usl=usl, spec_type=kind)
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
    db.add(spec_set)
    db.commit()
    return spec_set.items


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


@pytest.mark.skipif("issue_date" not in ExtractionResult.model_fields, reason="서버 칸은 feat/backend/extraction-doc-fields PR")
def test_document_dates_are_kept_in_the_result(auth_client, lioh_specs, ai_mode, db):
    # 판정 결과(JSON)에 남아 GET /extraction 으로 나가야 서버의 날짜 충돌·제품 불일치 검사가 읽을 수 있다
    r = upload(auth_client, FIXTURES / "COA_B_0005.pdf")
    doc = db.get(Document, r.json()["data"]["document_id"])
    db.refresh(doc)
    result = doc.extraction.result
    assert (result["issue_date"], result["expiry_date"], result["retest_date"]) == ("2026-02-26", "2027-02-21", None)
    assert "Lithium Hydroxide Monohydrate" in result["product_name"]
    got = auth_client.get(f"/api/v1/documents/{doc.id}/extraction").json()["data"]
    assert got["issue_date"] == "2026-02-26"


def test_upload_scanned_image_is_extracted_and_sent_to_review(auth_client, lioh_specs, ai_mode, db, tmp_path):
    """스캔본은 OCR 로 읽고, OCR 값은 모두 '원본 확인'으로 보내 로트를 보류한다 (숨은 불합격도 확인 뒤 판정)."""
    import pymupdf
    image = tmp_path / "scan.png"
    with pymupdf.open(FIXTURES / "COA_A_0007.pdf") as pdf:
        pdf[0].get_pixmap(dpi=200).save(image)
    r = upload(auth_client, image)
    doc = db.get(Document, r.json()["data"]["document_id"])
    db.refresh(doc)
    assert doc.status == "extracted", doc.error_message
    assert doc.lot_no == "SL25-0008"

    by_name = {i["normalized_name"]: i for i in doc.extraction.result["items"]}
    assert by_name["탄산"]["judgement"] == "check"
    assert by_name["탄산"]["judgement_reason"].startswith("추출 신뢰도 낮음")
    assert by_name["Na"]["bbox"]["page"] == 1
    assert doc.lot_recommendation == "hold"


def test_upload_broken_image_fails_with_reason(auth_client, lioh_specs, ai_mode, db, tmp_path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    r = upload(auth_client, image)
    doc = db.get(Document, r.json()["data"]["document_id"])
    db.refresh(doc)
    assert doc.status == "failed"
    assert doc.error_message.startswith("이미지 파일을 열 수 없습니다")
