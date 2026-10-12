"""[담당: 장수민] 문서 업로드·목록·상세·원본 조회 API 테스트 (명세 4.4~4.7). 실제 DB 필요."""
import json

import pytest

from app.core.config import settings
from app.core.enums import SpecType
from app.models import Document, SpecItem

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture
def specs(db):
    """탄산리튬 테스트용 규격 (실제 사내 규격 아님)."""
    rows = [
        SpecItem(material_code="LI2CO3", material_name="탄산리튬", item_name="순도", unit="%", lsl=99.5,
                 spec_type=SpecType.QUANTITATIVE, grade="D1", source="test"),
        SpecItem(material_code="LI2CO3", material_name="탄산리튬", item_name="Na", unit="ppm", usl=250,
                 spec_type=SpecType.QUANTITATIVE, grade="D1", source="test"),
        SpecItem(material_code="LI2CO3", material_name="탄산리튬", item_name="Fe", unit="ppm", usl=10,
                 spec_type=SpecType.QUANTITATIVE, grade="D1", source="test"),
        SpecItem(material_code="LI2CO3", material_name="탄산리튬", item_name="수분", unit="%", lsl=0, usl=0.4,
                 spec_type=SpecType.QUANTITATIVE, grade="D1", source="test"),
        SpecItem(material_code="LI2CO3", material_name="탄산리튬", item_name="Ca", unit="ppm", usl=50,
                 spec_type=SpecType.QUANTITATIVE, grade="D1", source="test"),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def upload(client, content=PDF, name="coa.pdf", material_code="LI2CO3", **form):
    return client.post(
        "/api/v1/documents",
        files={"file": (name, content, "application/octet-stream")},
        data={"material_code": material_code, **form},
    )


# ---- 업로드 (4.4) ----------------------------------------------------------
def test_upload_runs_extraction_and_judgement(auth_client, specs, db):
    r = upload(auth_client, supplier="수동입력 협력사", received_lot_no="IN-01")
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["status"] == "queued" and body["file_name"] == "coa.pdf"

    # TestClient 는 응답 뒤 BackgroundTasks 를 바로 실행한다 → 이미 extracted
    doc = db.get(Document, body["document_id"])
    db.refresh(doc)
    assert doc.status == "extracted"
    assert doc.supplier == "수동입력 협력사"            # 업로드 입력값 우선
    assert doc.lot_no == "LC-260920-01"                # 목업 추출 결과
    assert doc.material_name == "탄산리튬"
    result = doc.extraction.result
    by_name = {i["normalized_name"]: i for i in result["items"]}
    assert by_name["Fe"]["judgement"] == "check"       # 목업 confidence 0.74
    assert by_name["Ca"]["judgement"] == "missing"     # 규격에 있고 CoA 에 없음
    assert by_name["외관"]["judgement_reason"] == "규격 없음"
    assert doc.lot_recommendation == "hold" == result["lot_recommendation"]


def test_upload_png(auth_client, specs):
    assert upload(auth_client, PNG, "coa.png").status_code == 201


@pytest.mark.parametrize(
    "content, name",
    [(PDF, "coa.docx"), (PNG, "coa.pdf"), (b"", "coa.pdf"), (b"hello", "coa.jpg")],
    ids=["extension", "content-mismatch", "empty", "broken-jpg"],
)
def test_upload_invalid_file(auth_client, specs, content, name):
    r = upload(auth_client, content, name)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_FILE"


def test_upload_too_large(auth_client, specs, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)
    assert upload(auth_client).json()["error"]["code"] == "INVALID_FILE"


def test_upload_unknown_material(auth_client, specs):
    r = upload(auth_client, material_code="NICKEL")
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNKNOWN_MATERIAL"


def test_upload_requires_material_code(auth_client, specs):
    r = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_upload_requires_login(client, specs):
    r = upload(client)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_uploaded_file_saved_with_document_id(auth_client, specs, db):
    doc_id = upload(auth_client, name="한글 이름.pdf").json()["data"]["document_id"]
    doc = db.get(Document, doc_id)
    assert doc.file_path.endswith(f"{doc_id}.pdf") and doc.file_name == "한글 이름.pdf"


# ---- 추출 실패 → failed ----------------------------------------------------
def test_extraction_without_items_fails(auth_client, specs, db, tmp_path, monkeypatch):
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "empty.json").write_text(json.dumps({"items": []}))
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    doc_id = upload(auth_client, name="empty.pdf").json()["data"]["document_id"]
    d = auth_client.get(f"/api/v1/documents/{doc_id}").json()["data"]
    assert d["status"] == "failed" and d["error_message"] == "문서에서 시험 항목을 찾을 수 없습니다"


def test_extraction_bad_data_fails(auth_client, specs, tmp_path, monkeypatch):
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "bad.json").write_text(json.dumps({"items": [{"raw_value": "1"}]}))  # normalized_name 없음
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    doc_id = upload(auth_client, name="bad.pdf").json()["data"]["document_id"]
    d = auth_client.get(f"/api/v1/documents/{doc_id}").json()["data"]
    assert d["status"] == "failed" and d["error_message"]


# ---- 상세 (4.6) ------------------------------------------------------------
def test_detail(auth_client, specs):
    doc_id = upload(auth_client, received_lot_no="IN-01").json()["data"]["document_id"]
    r = auth_client.get(f"/api/v1/documents/{doc_id}")
    d = r.json()["data"]
    assert r.status_code == 200
    assert d["spec_grade"] == "D1" and d["applied_standard"] == "YS/T 582-2023 D1"
    assert d["test_date"] == "2026-09-20" and d["received_lot_no"] == "IN-01"
    assert d["uploaded_by"] == "김사용" and d["approved_by"] is None
    assert d["uploaded_at"].endswith("+09:00")


def test_detail_not_found(auth_client, specs):
    r = auth_client.get("/api/v1/documents/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# ---- 원본 파일 (4.7) -------------------------------------------------------
def test_file_download(auth_client, specs):
    doc_id = upload(auth_client, name="원본.pdf").json()["data"]["document_id"]
    r = auth_client.get(f"/api/v1/documents/{doc_id}/file")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")


def test_file_missing_on_disk(auth_client, specs, db):
    doc_id = upload(auth_client).json()["data"]["document_id"]
    doc = db.get(Document, doc_id)
    from pathlib import Path
    Path(doc.file_path).unlink()
    r = auth_client.get(f"/api/v1/documents/{doc_id}/file")
    assert r.status_code == 404 and r.json()["error"]["message"] == "원본 파일을 찾을 수 없습니다"


# ---- 목록 (4.5) ------------------------------------------------------------
def test_list_and_filters(auth_client, specs, admin, db):
    a = upload(auth_client, name="a.pdf").json()["data"]["document_id"]
    auth_client.login_as(admin)
    b = upload(auth_client, name="b.pdf").json()["data"]["document_id"]

    # 하나는 실패 상태로 만든다
    doc_b = db.get(Document, b)
    doc_b.status, doc_b.error_message, doc_b.lot_recommendation = "failed", "테스트 실패", None
    db.commit()

    r = auth_client.get("/api/v1/documents")
    data = r.json()["data"]
    assert data["total"] == 2 and [i["document_id"] for i in data["items"]] == [b, a]  # 최근 업로드 순

    item_a = next(i for i in data["items"] if i["document_id"] == a)
    assert item_a["summary"] == {"pass": 4, "fail": 0, "undetermined": 0, "missing": 1, "check": 1}  # 순도·Na·수분·외관 / Ca / Fe
    assert item_a["file_size"] == len(PDF) and item_a["uploaded_by"] == "김사용"

    def ids(q):
        return [i["document_id"] for i in auth_client.get(f"/api/v1/documents?{q}").json()["data"]["items"]]

    assert ids("status=failed") == [b]
    assert ids("status=extracted,in_review,on_hold") == [a]
    assert ids("lot_recommendation=hold") == [a]
    assert ids(f"uploaded_by={admin.id}") == [b]
    assert ids("page=2&size=1") == [a]


def test_list_summary_null_before_extraction(auth_client, specs, db, monkeypatch):
    monkeypatch.setattr("app.api.v1.documents.process_document", lambda _id: None)  # 추출 안 함
    upload(auth_client)
    item = auth_client.get("/api/v1/documents").json()["data"]["items"][0]
    assert item["status"] == "queued" and item["summary"] is None and item["lot_recommendation"] is None


def test_list_invalid_status(auth_client, specs):
    r = auth_client.get("/api/v1/documents?status=done")
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
