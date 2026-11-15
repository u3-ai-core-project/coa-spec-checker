"""[담당: 홍채령] 추출·판정 근거 버전 기록 테스트 (운영 정책 6장, app/services/version_service.py). 실제 DB 필요.

- 추출하면 어떤 추출기·프로그램·매핑 사전·규격 세트·정책으로 읽고 판정했는지 남는다 (GET /documents/{id} 의 versions)
- 같은 근거로 다시 판정(값 수정)하면 시각만 바뀌고, 규격 세트·규격이 바뀌면 이전 기록이 history 에 남는다
- 매핑 사전이 바뀌면 매핑 사전 지문이 바뀐다
- 엑셀 리포트에 "7. 판정 근거 버전" 이 나온다
- AI 결과 JSON(GET .../extraction) 형식은 그대로다
"""
import io

from openpyxl import load_workbook

from app import __version__
from app.core.config import settings
from app.services import mapping_service, version_service
from tests.api.test_rejudge import extraction, make_doc, rejudge  # noqa: F401  (make_doc 픽스처 재사용)


def versions(client, doc_id) -> dict:
    return client.get(f"/api/v1/documents/{doc_id}").json()["data"]["versions"]


def test_mock_extraction_records_versions(auth_client, make_doc):
    doc_id = make_doc("full")
    v = versions(auth_client, doc_id)
    e, j = v["extraction"], v["judgement"]
    assert e["extractor"] == "mock" and e["backend_version"] == __version__
    assert e["ai_package"] is None and e["llm"] == {"configured": False, "host": None, "model": None}
    assert e["mapping_dictionary"]["material_code"] == "LI2CO3"
    assert e["inquiry_drafter"] == settings.INQUIRY_DRAFTER and e["ai_reported"] == {}
    assert j["trigger"] == "extraction" and j["backend_version"] == __version__
    assert j["spec_set"]["code"] == "LI2CO3-D1-2023" and len(j["spec_set"]["rules_hash"]) == 12
    assert len(j["policy_hash"]) == 12
    assert v["history"] == []


def test_ai_result_json_unchanged(auth_client, make_doc):
    """AI 결과 JSON(명세 2.1) 에는 버전 칸을 넣지 않는다."""
    doc_id = make_doc("full")
    assert "versions" not in extraction(auth_client, doc_id)


def test_review_with_same_basis_does_not_grow_history(auth_client, make_doc):
    doc_id = make_doc("full")
    before = versions(auth_client, doc_id)["judgement"]
    items = extraction(auth_client, doc_id)["items"]
    na = next(i for i in items if i["normalized_name"] == "Na")
    r = auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{na['item_id']}/confirm")
    assert r.status_code == 200
    v = versions(auth_client, doc_id)
    assert v["judgement"]["trigger"] == "review"
    assert v["judgement"]["spec_set"] == before["spec_set"] and v["judgement"]["policy_hash"] == before["policy_hash"]
    assert v["history"] == []


def test_respec_keeps_previous_in_history(auth_client, make_doc):
    doc_id = make_doc("full")
    assert rejudge(auth_client, doc_id, "LI2CO3-D1-RELAXED", apply=True, reason="완화 기준 확인").status_code == 200
    v = versions(auth_client, doc_id)
    assert (v["judgement"]["trigger"], v["judgement"]["spec_set"]["code"]) == ("respec", "LI2CO3-D1-RELAXED")
    [old] = v["history"]
    assert (old["judgement"]["trigger"], old["judgement"]["spec_set"]["code"]) == ("extraction", "LI2CO3-D1-2023")
    assert "extraction" not in old                     # 다시 읽은 것이 아니므로 추출 기록은 그대로
    assert v["extraction"]["extractor"] == "mock"


def test_spec_edit_changes_rules_hash(auth_client, make_doc, admin):
    doc_id = make_doc("full")
    before = versions(auth_client, doc_id)["judgement"]["spec_set"]["rules_hash"]
    specs = auth_client.get("/api/v1/specs", params={"spec_set_code": "LI2CO3-D1-2023"}).json()["data"]
    na = next(s for s in specs if s["item_name"] == "Na")
    auth_client.login_as(admin)
    r = auth_client.patch(f"/api/v1/specs/{na['id']}", json={"usl": 60, "reason": "규격 개정", "rejudge": True})
    assert r.status_code == 200
    v = versions(auth_client, doc_id)
    assert v["judgement"]["trigger"] == "spec_change"
    assert v["judgement"]["spec_set"]["rules_hash"] != before
    assert v["history"][-1]["judgement"]["spec_set"]["rules_hash"] == before


def test_retry_extraction_moves_old_record_to_history(auth_client, make_doc, db):
    from app.core.enums import DocumentStatus
    from app.models import Document
    from app.pipeline.worker import process_document
    doc_id = make_doc("full")
    first = versions(auth_client, doc_id)
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.QUEUED
    db.commit()
    process_document(doc_id)
    v = versions(auth_client, doc_id)
    assert v["extraction"]["read_at"] != first["extraction"]["read_at"]
    assert v["history"][-1]["extraction"] == first["extraction"]


def test_mapping_change_changes_mapping_version(db, user):
    before = version_service.mapping_version(db, "LI2CO3")
    mapping_service.upsert_manual(db, material_code="LI2CO3", raw_name="Natrium", normalized_name="Na", user_id=user.id)
    db.commit()
    after = version_service.mapping_version(db, "LI2CO3")
    assert after["count"] == before["count"] + 1 and after["hash"] != before["hash"]
    assert after["latest_created_at"] is not None
    # 다른 원자재 사전은 영향 없음
    assert version_service.mapping_version(db, "NIOH2")["count"] == 0


def test_llm_host_only(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://user:pw@llm.local:8090/v1/chat?key=secret")
    assert version_service.llm_info() == {"configured": True, "host": "llm.local:8090", "model": None}
    monkeypatch.setattr(settings, "LLM_BASE_URL", None)
    assert version_service.llm_info()["configured"] is False


def test_ai_package_missing_is_null(monkeypatch):
    def missing(name):
        raise version_service.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(version_service.metadata, "version", missing)
    assert version_service.ai_package_info() is None


def test_ai_extractor_records_ai_package(db, user, monkeypatch):
    """설치된 coa-ai 의 버전(ai/pyproject.toml 의 version)을 남긴다. 이 테스트는 설치 여부와 상관없게 버전 조회를 바꿔 끼운다."""
    monkeypatch.setattr(version_service.metadata, "version", lambda name: "0.1.0")
    info = version_service.ai_package_info()
    from app.models import Document
    monkeypatch.setattr(settings, "EXTRACTOR", "ai")
    doc = Document(id="x", file_name="a.pdf", file_path="", content_type="application/pdf", material_code="LI2CO3",
                   uploaded_by=user.id)
    rec = version_service.extraction_record(db, doc, {"model": "gemma-3", "items": []})
    assert rec["extractor"] == "ai" and rec["ai_package"] == info and info["name"] == "coa-ai"
    assert rec["ai_reported"] == {"model": "gemma-3"}   # AI 결과에 버전 같은 칸이 있으면 그대로 남긴다


def test_policy_setting_changes_policy_hash(monkeypatch):
    before = version_service.policy_hash()
    monkeypatch.setattr(settings, "ND_LIMIT_INCLUSIVE", not settings.ND_LIMIT_INCLUSIVE)
    assert version_service.policy_hash() != before


def test_report_has_version_section(auth_client, make_doc):
    doc_id = make_doc("full")
    r = auth_client.get(f"/api/v1/documents/{doc_id}/report")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    rows = [tuple(v for v in row if v is not None) for row in ws.iter_rows(values_only=True)]
    assert ("7. 판정 근거 버전",) in rows
    values = {row[0]: row[1] for row in rows if len(row) == 2}
    assert values["추출기"] == "mock"
    assert values["LLM"] == "사용 안 함"
    assert values["판정 규격"] == "LI2CO3-D1-2023 / YS/T 582-2023"
    assert values["프로그램 버전"] == f"백엔드 {__version__}"
    assert values["매핑 사전"].endswith(versions(auth_client, doc_id)["extraction"]["mapping_dictionary"]["hash"])


def test_report_without_versions_says_no_record(auth_client, make_doc, db):
    from app.models import Document
    doc_id = make_doc("full")
    doc = db.get(Document, doc_id)
    doc.extraction.versions = None   # 기능 전에 처리된 문서
    db.commit()
    r = auth_client.get(f"/api/v1/documents/{doc_id}/report")
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    flat = [v for row in ws.iter_rows(values_only=True) for v in row if v is not None]
    assert "기록 없음 (버전 기록 기능 전에 처리된 문서)" in flat
