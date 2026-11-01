"""[담당: 장수민] 일괄 접수 테스트 (멘토님 UC01·UC07, UC10 검토 큐. 명세 v1.4 4.4-1, 4.4-2). 실제 DB 필요."""
import json

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Document
from seeds.seed_specs import seed_specs
from tests.api.test_demo20_acceptance import CASES, build_coa

PDF = b"%PDF-1.7\n" + b"0" * 50
HEADER = "receipt_id,supplier,material,received_lot,spec_id,received_date,file_name\n"


@pytest.fixture
def batch(auth_client, db, tmp_path, monkeypatch):
    """batch(coas={파일 이름(확장자 제외): 목업 추출 JSON}, csv=..., files=[(이름, 내용)]) → (응답 코드, data|error)."""
    seed_specs(db)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    monkeypatch.setattr(settings, "UNMAPPED_AI_ITEM", "check")

    def _batch(coas: dict[str, dict] | None = None, *, csv: str | bytes | None = None, files=None,
               spec_set_code: str | None = None):
        for name, coa in (coas or {}).items():
            (mock_dir / f"{name}.json").write_text(json.dumps(coa, ensure_ascii=False), encoding="utf-8")
        upload = [("files", (f"{n}.pdf", PDF, "application/pdf")) for n in (coas or {})]
        upload += [("files", (n, content, "application/octet-stream")) for n, content in (files or [])]
        if csv is not None:
            upload.append(("receipts", ("receipts.csv", csv.encode() if isinstance(csv, str) else csv, "text/csv")))
        data = {"material_code": "LI2CO3"}
        if spec_set_code:
            data["spec_set_code"] = spec_set_code
        r = auth_client.post("/api/v1/documents/batch", files=upload, data=data)
        body = r.json()
        return r.status_code, body["data"] if body["success"] else body["error"]
    return _batch


def coa(lot: str, **values) -> dict:
    """base CoA 를 로트번호와 일부 값만 바꿔서. 예) coa("L-1", Na="80")"""
    return build_coa({"set": {k: {"raw_value": v} for k, v in values.items()}}, lot_no=lot)


def detail(auth_client, batch_id: str) -> dict:
    r = auth_client.get(f"/api/v1/documents/batch/{batch_id}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def by_file(detail_data: dict) -> dict:
    return {i["file_name"]: i for i in detail_data["queue"] + detail_data["isolated"]}


# ---- 입고 정보 연결 ----------------------------------------------------------
def test_link_by_file_name_and_by_lot(batch, auth_client):
    csv = HEADER + ("R1,알파,LI2CO3,LOT-A,,2026-10-01,a.pdf\n"
                    "R2,베타,LI2CO3,LOT-B,LI2CO3-D3-2023,2026-10-01,\n"
                    "R3,감마,LI2CO3,LOT-X,,,\n")
    code, up = batch({"a": coa("LOT-A"), "b": coa("lot b", Na="80"), "c": coa("LOT-C")}, csv=csv)
    assert code == 201
    assert (up["receipts"], up["linked_by_file"], up["rejected"]) == (3, 1, [])
    assert {d["file_name"]: d["receipt_id"] for d in up["documents"]} == {"a.pdf": "R1", "b.pdf": None, "c.pdf": None}

    d = detail(auth_client, up["batch_id"])
    docs = by_file(d)
    # a: file_name 으로 연결, 입고 CSV 의 공급사 사용
    assert (docs["a.pdf"]["receipt_id"], docs["a.pdf"]["supplier"], docs["a.pdf"]["document_issues"]) == ("R1", "알파", [])
    # b: CoA 로트 "lot b" = 입고 로트 "LOT-B" (표기 차이 무시) → 연결되고 입고 행의 D3 세트로 판정 (Na 80 적합)
    assert (docs["b.pdf"]["receipt_id"], docs["b.pdf"]["received_lot_no"], docs["b.pdf"]["spec_set_code"]) == \
           ("R2", "LOT-B", "LI2CO3-D3-2023")
    assert docs["b.pdf"]["lot_recommendation"] == "approve"
    # c: 입고 정보에 없는 로트 → 서류 불일치, 보류
    assert docs["c.pdf"]["document_issues"] == ["LOT_MISMATCH"] and docs["c.pdf"]["lot_recommendation"] == "hold"
    # R3: CoA 미접수
    assert [r["receipt_id"] for r in d["unmatched_receipts"]] == ["R3"]


def test_lot_mismatch_message_and_follow_up(batch, auth_client):
    code, up = batch({"c": coa("LOT-C")}, csv=HEADER + "R1,,,LOT-A,,,\n")
    doc_id = up["documents"][0]["document_id"]
    result = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]
    assert result["document_issues"][0]["message"] == "입고 정보에 CoA 로트 LOT-C 가 없습니다"
    f = auth_client.get(f"/api/v1/documents/{doc_id}/follow-ups").json()["data"]
    assert f["suggested_follow_up"] == "request_correct_coa"


def test_file_linked_receipt_with_different_lot_is_mismatch(batch, auth_client):
    """file_name 으로 연결했는데 CoA 로트가 입고 로트와 다르면 LOT_MISMATCH (데모 12)."""
    code, up = batch({"a": coa("LOT-A")}, csv=HEADER + "R1,,,LOT-Z,,,a.pdf\n")
    item = by_file(detail(auth_client, up["batch_id"]))["a.pdf"]
    assert (item["received_lot_no"], item["document_issues"]) == ("LOT-Z", ["LOT_MISMATCH"])


def test_received_date_after_expiry_is_date_conflict(batch, auth_client):
    """입고 CSV 의 입고일이 CoA 유효기한을 지나면 DATE_CONFLICT (file_name 연결, 로트 연결 모두)."""
    expired = {**coa("LOT-A"), "expiry_date": "2026-09-30"}
    fresh = {**coa("LOT-B"), "expiry_date": "2027-09-30"}
    csv = HEADER + "R1,,,LOT-A,,2026-10-05,a.pdf\nR2,,,LOT-B,,2026-10-05,\n"
    code, up = batch({"a": expired, "b": fresh}, csv=csv)
    docs = by_file(detail(auth_client, up["batch_id"]))
    assert docs["a.pdf"]["document_issues"] == ["DATE_CONFLICT"] and docs["a.pdf"]["lot_recommendation"] == "hold"
    assert docs["b.pdf"]["document_issues"] == []
    msg = auth_client.get(f"/api/v1/documents/{docs['a.pdf']['document_id']}/extraction").json()["data"]
    assert "입고일 2026-10-05이 유효기한 2026-09-30을 지남" in msg["document_issues"][0]["message"]


def test_received_date_checked_after_lot_link(batch, auth_client):
    expired = {**coa("LOT-B"), "retest_date": "2026-08-01"}
    code, up = batch({"b": expired}, csv=HEADER + "R2,,,LOT-B,,2026-10-05,\n")
    item = by_file(detail(auth_client, up["batch_id"]))["b.pdf"]
    assert (item["receipt_id"], item["document_issues"]) == ("R2", ["DATE_CONFLICT"])


def test_same_lot_different_material_is_product_mismatch(batch, auth_client, db):
    """로트는 맞는데 입고 원자재가 다르면 PRODUCT_MISMATCH (생성기 v2 MATERIAL_MISMATCH). 입고 건은 연결된다."""
    code, up = batch({"a": coa("LOT-A")}, csv=HEADER + "R1,,LIOH,LOT-A,,,\n")
    d = detail(auth_client, up["batch_id"])
    item = by_file(d)["a.pdf"]
    assert (item["receipt_id"], item["document_issues"], item["spec_set_code"]) == \
           ("R1", ["PRODUCT_MISMATCH"], "LI2CO3-D1-2023")
    assert d["unmatched_receipts"] == []
    f = auth_client.get(f"/api/v1/documents/{item['document_id']}/follow-ups").json()["data"]
    assert f["suggested_follow_up"] == "request_correct_coa"


def test_two_coas_for_one_received_lot(batch, auth_client):
    code, up = batch({"b1": coa("LOT-B"), "b2": coa("LOT-B")}, csv=HEADER + "R1,,,LOT-B,,,\n")
    docs = by_file(detail(auth_client, up["batch_id"]))
    assert docs["b1.pdf"]["receipt_id"] == "R1" and docs["b1.pdf"]["document_issues"] == []
    assert docs["b2.pdf"]["receipt_id"] is None and docs["b2.pdf"]["document_issues"] == ["LOT_MISMATCH"]
    doc_id = docs["b2.pdf"]["document_id"]
    msg = auth_client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["document_issues"][0]["message"]
    assert "이미 다른 CoA" in msg


def test_without_receipts_no_lot_check(batch, auth_client):
    code, up = batch({"a": coa("LOT-A"), "b": coa("LOT-B")})
    assert code == 201 and up["receipts"] == 0
    d = detail(auth_client, up["batch_id"])
    assert all(i["document_issues"] == [] for i in d["queue"]) and d["unmatched_receipts"] == []


def test_default_spec_set_applies_to_unlinked_files(batch, auth_client):
    code, up = batch({"a": coa("LOT-A", Na="80")}, spec_set_code="LI2CO3-D3-2023")
    item = by_file(detail(auth_client, up["batch_id"]))["a.pdf"]
    assert (item["spec_set_code"], item["lot_recommendation"]) == ("LI2CO3-D3-2023", "approve")


# ---- 검토 큐 (UC10) -----------------------------------------------------------
def test_queue_order(batch, auth_client):
    csv = HEADER + "R1,,,LOT-A,,,\nR2,,,LOT-B,,,\nR4,,,LOT-D,,,\n"
    code, up = batch({"ok": coa("LOT-B"), "nd": coa("LOT-D", Fe="ND"), "unknown": coa("LOT-C"), "oos": coa("LOT-A", Na="80")},
                     csv=csv)
    d = detail(auth_client, up["batch_id"])
    assert [i["file_name"] for i in d["queue"]] == ["oos.pdf", "unknown.pdf", "nd.pdf", "ok.pdf"]
    assert [i["priority_label"] for i in d["queue"]] == ["부적합", "서류 불일치", "판정 불가·누락·확인 필요", "정상"]
    assert d["summary"] == {"total": 4, "reject": 1, "document_issue": 1, "hold": 1, "approve": 1, "processing": 0,
                            "isolated": 0}


def test_demo_lots_as_one_batch(batch, auth_client):
    """멘토님 데모 로트(단일 로트 사례 중 구현된 18건)를 한 묶음으로 올려도 사례별 권고가 같고, 검토 큐가 순서대로 나온다 (UC10 20건 혼합 배치)."""
    cases = [c for c in CASES if not c.get("pending") and "repeat_lots" not in c]   # 데모 20 은 여러 로트 사례
    coas, rows = {}, []
    for c in cases:
        name, lot = f'demo{c["id"]}', f'DEMO-L{c["id"]}'
        coas[name] = build_coa(c.get("patch"), lot_no=lot)
        received = c.get("received_lot_no") or lot            # 데모 12 는 입고 로트가 다름
        rows.append(f'R{c["id"]},,,{received},{c.get("spec_set", "")},,{name}.pdf')
    code, up = batch(coas, csv=HEADER + "\n".join(rows) + "\n")
    assert code == 201 and up["linked_by_file"] == len(cases)

    d = detail(auth_client, up["batch_id"])
    got = {i["file_name"]: i["lot_recommendation"] for i in d["queue"]}
    assert got == {f'demo{c["id"]}.pdf': c["expected"]["lot_recommendation"] for c in cases}
    priorities = [i["priority"] for i in d["queue"]]
    assert priorities == sorted(priorities) and d["isolated"] == [] and d["unmatched_receipts"] == []
    issue_files = {i["file_name"] for i in d["queue"] if i["document_issues"]}
    assert issue_files == {"demo12.pdf", "demo18.pdf"}


# ---- 오류 문서 격리 -----------------------------------------------------------
def test_invalid_file_rejected_others_accepted(batch, auth_client):
    code, up = batch({"a": coa("LOT-A")}, files=[("memo.txt", b"hello"), ("broken.pdf", b"not a pdf")])
    assert code == 201
    assert [d["file_name"] for d in up["documents"]] == ["a.pdf"]
    assert [(r["file_name"], r["code"]) for r in up["rejected"]] == [("memo.txt", "INVALID_FILE"), ("broken.pdf", "INVALID_FILE")]


def test_extraction_failure_isolated(batch, auth_client):
    """목업 JSON 이 없는 파일 = 추출 실패 (CoA 가 아닌 문서 등) → 격리 목록."""
    code, up = batch({"a": coa("LOT-A")}, files=[("spec_sheet.pdf", PDF)])
    d = detail(auth_client, up["batch_id"])
    assert [i["file_name"] for i in d["isolated"]] == ["spec_sheet.pdf"]
    assert d["isolated"][0]["status"] == "failed" and d["isolated"][0]["priority_label"] == "격리(추출 실패)"
    assert [i["file_name"] for i in d["queue"]] == ["a.pdf"] and d["summary"]["isolated"] == 1


# ---- 입고 CSV 검사 ------------------------------------------------------------
@pytest.mark.parametrize("csv, message", [
    ("receipt_id,supplier\nR1,알파\n", "received_lot 열이 필요합니다"),
    (HEADER + "R1,,,LOT-A,,,\nR1,,,LOT-B,,,\n", "3행: receipt_id R1 가 중복됩니다"),
    (HEADER + "R1,,,LOT-A,,,\nR2,,,lot a,,,\n", "3행: 입고 로트 lot a 가 중복됩니다"),
    (HEADER + "R1,,,LOT-A,,10/01/2026,\n", "2행: received_date 는 YYYY-MM-DD"),
    (HEADER + "R1,,,LOT-A,NO-SUCH-SET,,\n", "2행: LI2CO3 에 등록되지 않은 규격 세트입니다"),
    (HEADER + "R1,,NICKEL,LOT-A,,,\n", "2행: 등록되지 않은 원자재 구분입니다"),
    (HEADER + ",,,LOT-A,,,\n", "2행: receipt_id, received_lot 은 비울 수 없습니다"),
])
def test_invalid_csv_saves_nothing(batch, db, csv, message):
    code, err = batch({"a": coa("LOT-A")}, csv=csv)
    assert (code, err["code"]) == (400, "VALIDATION_ERROR")
    assert message in err["message"]
    assert db.scalar(select(func.count()).select_from(Document)) == 0


def test_csv_cp949_and_column_aliases(batch, auth_client):
    csv = "receipt_id,supplier,received_lot_no,spec_set_code,received_date\nR1,알파 리튬,LOT-A,LI2CO3-D3-2023,2026/10/01\n"
    code, up = batch({"a": coa("LOT-A", Na="80")}, csv=csv.encode("cp949"))
    assert code == 201
    item = by_file(detail(auth_client, up["batch_id"]))["a.pdf"]
    assert (item["receipt_id"], item["supplier"], item["spec_set_code"], item["lot_recommendation"]) == \
           ("R1", "알파 리튬", "LI2CO3-D3-2023", "approve")


def test_too_many_files(batch, monkeypatch):
    monkeypatch.setattr(settings, "MAX_BATCH_FILES", 2)
    code, err = batch({"a": coa("A"), "b": coa("B"), "c": coa("C")})
    assert (code, err["code"]) == (400, "VALIDATION_ERROR") and "2개까지" in err["message"]


def test_unknown_material(auth_client, db):
    r = auth_client.post("/api/v1/documents/batch", files=[("files", ("a.pdf", PDF, "application/pdf"))],
                         data={"material_code": "NICKEL"})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "UNKNOWN_MATERIAL")


# ---- 조회 ------------------------------------------------------------------
def test_unknown_batch_404(auth_client, db):
    r = auth_client.get("/api/v1/documents/batch/no-such-batch")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_document_list_filter_and_detail_batch_id(batch, auth_client):
    code, up = batch({"a": coa("A"), "b": coa("B")})
    auth_client.post("/api/v1/documents", files={"file": ("single.pdf", PDF)}, data={"material_code": "LI2CO3"})
    listed = auth_client.get("/api/v1/documents", params={"batch_id": up["batch_id"]}).json()["data"]
    assert listed["total"] == 2 and {i["file_name"] for i in listed["items"]} == {"a.pdf", "b.pdf"}
    doc_id = up["documents"][0]["document_id"]
    assert auth_client.get(f"/api/v1/documents/{doc_id}").json()["data"]["batch_id"] == up["batch_id"]


def test_requires_login(client, db):
    r = client.post("/api/v1/documents/batch", files=[("files", ("a.pdf", PDF, "application/pdf"))],
                    data={"material_code": "LI2CO3"})
    assert r.status_code == 401
