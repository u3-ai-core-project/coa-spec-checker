"""[담당: 장수민] 엑셀 리포트 테스트 (명세 4.16, v1.4안). 실제 DB 필요.

내려받은 파일을 openpyxl 로 다시 열어 내용이 맞는지 본다.
"""
import io
import json
from urllib.parse import unquote

import pytest
from openpyxl import load_workbook

from app.core.config import settings
from app.core.enums import DocumentStatus, SpecType
from app.models import Document, SpecItem, SpecSet
from app.services import report_service

PDF = b"%PDF-1.7\n%test\n" + b"0" * 100
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MOCK = {  # 실제 CoA 아님
    "supplier": "테스트 공급사",
    "lot_no": "A0481544",
    "test_date": "2026-01-15",
    "items": [
        {"raw_name": "Sodium (Na)", "normalized_name": "Na", "mapping_source": "dictionary",
         "raw_value": "80", "raw_spec": "=<100", "unit": "ppm", "confidence": 0.95},       # 부적합
        {"raw_name": "Iron (Fe)", "normalized_name": "Fe", "mapping_source": "dictionary",
         "raw_value": "none detected", "unit": "ppm", "confidence": 0.95},                  # 확인 필요 (ND_NO_LOD)
        {"raw_name": "Assay", "normalized_name": "순도", "mapping_source": "dictionary",
         "raw_value": "99.6", "unit": "%", "confidence": 0.6},                               # 신뢰도 낮음
    ],
}


@pytest.fixture
def doc_id(auth_client, db, tmp_path, monkeypatch):
    q = SpecType.QUANTITATIVE
    spec_set = SpecSet(code="LI2CO3-D1-T", material_code="LI2CO3", material_name="탄산리튬",
                       grade="D1", version="YS/T 582-2023", is_default=True)
    spec_set.items = [SpecItem(item_name="Na", unit="ppm", usl=50, spec_type=q),
                      SpecItem(item_name="Fe", unit="ppm", usl=5, spec_type=q),
                      SpecItem(item_name="순도", unit="%", lsl=99.5, spec_type=q),
                      SpecItem(item_name="Mg", unit="ppm", usl=10, spec_type=q)]       # 누락
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "coa.json").write_text(json.dumps(MOCK, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    r = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)},
                         data={"material_code": "LI2CO3", "received_lot_no": "IN-7"})
    return r.json()["data"]["document_id"]


def download(client, doc_id):
    r = client.get(f"/api/v1/documents/{doc_id}/report")
    assert r.status_code == 200, r.text
    return r, load_workbook(io.BytesIO(r.content))


def cells(ws) -> list[tuple]:
    return [tuple(row) for row in ws.iter_rows(values_only=True)]


def packed(row) -> tuple:
    """합친 셀의 빈칸(None)을 빼고 값만. 이력 표처럼 여러 열을 합친 행 비교용 (값이 빈 칸도 빠짐에 주의)."""
    return tuple(v for v in row if v is not None)


def find_value(rows, label):
    """'항목명 | 값' 표에서 값 (항목명 다음의 첫 값, 값이 비었으면 None)."""
    row = next(r for r in rows if r[0] == label)
    return next((v for v in row[1:] if v is not None), None)


def table(rows, header_first: str, header_second: str) -> list[tuple]:
    """머리글(빈칸 뺀 첫 두 값으로 찾음) 다음 행부터 빈 행·다음 구역 전까지."""
    start = next(n for n, r in enumerate(rows) if packed(r)[:2] == (header_first, header_second))
    out = []
    for r in rows[start + 1:]:
        if r[0] is None or str(r[0]).startswith(("4.", "5.", "6.", "메일")) or r[0] == "기록 없음":
            break
        out.append(r)
    return out


# ---- 기본 구성 --------------------------------------------------------------
def test_report_headers_and_sheets(auth_client, doc_id):
    r, wb = download(auth_client, doc_id)
    assert r.headers["content-type"] == XLSX
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert unquote(disposition.split("filename*=UTF-8''")[1]).startswith("CoA검수리포트_A0481544_")
    assert wb.sheetnames == ["A0481544", "문의 초안"]


def test_document_info_and_summary(auth_client, doc_id):
    _, wb = download(auth_client, doc_id)
    rows = cells(wb["A0481544"])
    assert find_value(rows, "협력사") == "테스트 공급사"
    assert find_value(rows, "입고 로트번호") == "IN-7"
    assert find_value(rows, "시험일") == "2026-01-15"
    assert find_value(rows, "사내 규격") == "LI2CO3-D1-T / D1 YS/T 582-2023"
    assert find_value(rows, "로트 권고") == "불합격 권고"
    assert find_value(rows, "판정별 항목 수") == "적합 0 · 부적합 1 · 판정 불가 0 · 누락 1 · 확인 필요 2"


def test_item_table_order_and_v14_columns(auth_client, doc_id):
    _, wb = download(auth_client, doc_id)
    rows = cells(wb["A0481544"])
    header = next(r for r in rows if r[0] == "No")
    assert header[11:13] == ("사유코드", "해결 조건")
    items = table(rows, "No", "항목")
    # 부적합 → 확인 필요 → 누락 순 (명세 4.8)
    assert [r[1] for r in items] == ["Na", "Fe", "순도", "Mg"]
    na = items[0]
    assert (na[3], na[5], na[6], na[7], na[8], na[10]) == ("80", "=<100", "80", "≤ 50", "부적합", 30)
    assert na[11].startswith("OUT_OF_SPEC") and "단위·표기" in na[12]
    fe = items[1]
    assert fe[8] == "확인 필요" and fe[11].startswith("ND_NO_LOD") and fe[12] == "검출한계 ≤ 5 ppm (또는 정량값)"
    assert items[3][8] == "누락" and items[3][11].startswith("MISSING_REQUIRED")


def test_unapproved_document_has_blank_decision(auth_client, doc_id):
    _, wb = download(auth_client, doc_id)
    rows = cells(wb["A0481544"])
    assert find_value(rows, "AI 권고") == "불합격 권고"
    assert find_value(rows, "최종 처분") is None and find_value(rows, "처분자") is None
    assert any(r[0] == "기록 없음" for r in rows)   # 이력이 아직 없음


# ---- 이력과 처분 ------------------------------------------------------------
def test_logs_and_final_decision(auth_client, doc_id):
    items = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]
    ids = {i["normalized_name"]: i["item_id"] for i in items}
    auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{ids['순도']}/confirm")
    auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{ids['Fe']}",
                      json={"detection_limit": 2, "value_source": "supplier_reply", "reason": "공급사 회신 메일"})
    auth_client.post(f"/api/v1/documents/{doc_id}/hold", json={"follow_up": "internal_test", "reason": "Mg 자체 시험"})
    auth_client.post(f"/api/v1/documents/{doc_id}/approve",
                     json={"decision": "conditional_accept", "reason": "Na 초과분 혼합 사용"})

    _, wb = download(auth_client, doc_id)
    rows = cells(wb["A0481544"])
    review = table(rows, "일시", "항목")
    # 열: 일시(A:B) 항목(C) 작업(D) 이전 값(E:F) 이후 값(G:H) 입력 출처(I) 사유(J:M) 담당자(N:O)
    assert [(r[2], r[3], r[8], r[9], r[13]) for r in review] == [
        ("순도", "값 확인", None, None, "김사용"),
        ("Fe", "값 수정", "공급사 회신", "공급사 회신 메일", "김사용"),
    ]
    assert (review[1][4], review[1][6]) == ("none detected", "검출 안 됨 (검출한계 2 ppm)")
    approvals = table(rows, "일시", "작업")
    # 열: 일시(A:B) 작업(C) 처분(D) 후속 조치(E:G) 사유(H:M) 담당자(N:O)
    assert [(r[2], r[3], r[4]) for r in approvals] == [("보류", None, "자체 시험"), ("처분", "조건부 승인", None)]
    assert find_value(rows, "최종 처분") == "조건부 승인"
    assert find_value(rows, "처분자") == "김사용"
    assert find_value(rows, "처분 사유") == "Na 초과분 혼합 사용"
    # 처리 후 항목표의 검수 칸
    item_rows = {r[1]: r for r in table(rows, "No", "항목")}
    assert item_rows["Fe"][14] == "공급사 회신" and item_rows["순도"][14] == "확인함"


# ---- 문의 초안 시트 (v1.4안) ----------------------------------------------------
def test_inquiry_sheet(auth_client, doc_id):
    _, wb = download(auth_client, doc_id)
    rows = cells(wb["문의 초안"])
    lines = table(rows, "로트", "대상")
    by_target = {r[1]: r for r in lines}
    assert by_target["Na"][6] == "공급사" and by_target["Fe"][6] == "공급사" and by_target["Mg"][6] == "공급사"
    assert by_target["순도"][6] == "내부 확인"                 # 신뢰도 낮음은 내부에서 원문 확인
    assert lines[0][1] == "Na"                                # 부적합이 맨 앞
    subject = find_value(rows, "메일 제목")
    body = find_value(rows, "메일 본문")
    assert subject == "[CoA 확인 요청] 탄산리튬 / Lot A0481544"
    assert 'Fe (CoA 기재: "none detected")' in body and "검출한계 ≤ 5 ppm" in body
    assert "CoA 에 없는 항목: Mg" in body                      # 누락 항목은 한 번호로 묶음
    assert "재시험 가능 여부" in body                          # 부적합은 공급사용 문구로
    assert "순도" not in body                                  # 내부 확인 항목은 메일에 넣지 않음


# ---- 오류 -------------------------------------------------------------------
def test_not_found(auth_client, doc_id):
    r = auth_client.get("/api/v1/documents/nope/report")
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_not_ready(auth_client, doc_id, db):
    doc = db.get(Document, doc_id)
    doc.status = DocumentStatus.PROCESSING
    db.commit()
    r = auth_client.get(f"/api/v1/documents/{doc_id}/report")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_READY"


def test_generation_failure_returns_500(auth_client, doc_id, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("disk full")
    monkeypatch.setattr(report_service, "build_workbook", boom)
    r = auth_client.get(f"/api/v1/documents/{doc_id}/report")
    assert r.status_code == 500 and r.json()["error"]["code"] == "REPORT_GENERATION_FAILED"


def test_requires_login(client, auth_client, doc_id):
    from app.api.deps import get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get(f"/api/v1/documents/{doc_id}/report").status_code == 401


# ---- 여러 건 (리포트 화면 여러 건 다운로드 대비) ------------------------------------
def test_workbook_with_same_lot_twice(auth_client, doc_id, db):
    second = auth_client.post("/api/v1/documents", files={"file": ("coa.pdf", PDF)},
                              data={"material_code": "LI2CO3"}).json()["data"]["document_id"]
    docs = [db.get(Document, doc_id), db.get(Document, second)]
    wb = load_workbook(io.BytesIO(report_service.build_workbook(db, docs)))
    assert wb.sheetnames == ["A0481544", "A0481544(2)", "문의 초안"]


# ---- 수식 주입 방지 -----------------------------------------------------------
def test_text_starting_with_equals_is_not_a_formula(auth_client, doc_id):
    """CoA 원문 "=<100" 이 수식으로 저장되면 엑셀에서 오류가 나고, 악성 문서면 수식이 실행될 수 있다."""
    _, wb = download(auth_client, doc_id)
    ws = wb["A0481544"]
    cell = next(c for row in ws.iter_rows() for c in row if c.value == "=<100")
    assert cell.data_type == "s"
