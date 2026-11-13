"""[담당: 홍채령] 삭제 기록 테스트 (운영 정책 1장). 실제 DB 필요.

삭제할 때 누가·언제·무엇을·왜 + 삭제 직전 처분·검수 이력 요약이 deletion_logs 에 남는지,
문서 내용(추출 값)이 들어가지 않는지, 조회 API 가 ADMIN 전용인지 본다.
"""
import json

from sqlalchemy import func, select

from app.models import DeletionLog
from tests.api.test_document_delete import delete, make_doc  # noqa: F401 (fixture)

LOGS = "/api/v1/deletion-logs"


def items(client, doc_id):
    return client.get(f"/api/v1/documents/{doc_id}/extraction").json()["data"]["items"]


def test_log_written_with_summaries(auth_client, make_doc, user, admin, db):
    doc_id = make_doc()
    na = items(auth_client, doc_id)[0]["item_id"]
    # 값 수정 1번, 확인 1번, 보류 1번
    r = auth_client.patch(f"/api/v1/documents/{doc_id}/extraction/{na}",
                          json={"converted_value": 77.7, "reason": "오타 수정"})
    assert r.status_code == 200, r.text
    assert auth_client.post(f"/api/v1/documents/{doc_id}/extraction/{na}/confirm").status_code == 200
    assert auth_client.post(f"/api/v1/documents/{doc_id}/hold",
                            json={"follow_up": "request_detection_limit", "reason": "검출한계 요청"}).status_code == 200

    assert delete(auth_client, doc_id, reason="  공급사가 다른 로트 문서를 보냄  ").status_code == 200

    log = db.scalar(select(DeletionLog))
    assert log.document_id == doc_id
    assert log.file_name == "doc.pdf" and log.material_code == "LI2CO3"
    assert log.status_at_delete == "on_hold"
    assert log.uploaded_by == user.id and log.deleted_by == user.id
    assert log.reason == "공급사가 다른 로트 문서를 보냄"  # 앞뒤 공백 제거
    assert log.rule.value == "manual"
    assert log.file_size > 0 and len(log.file_sha256) == 64
    assert log.approval_summary == [{
        "action": "hold", "decision": None, "follow_up": "request_detection_limit",
        "user_id": user.id, "at": log.approval_summary[0]["at"], "reason": "검출한계 요청",
    }]
    rs = log.review_summary
    assert rs["counts"] == {"edit": 1, "confirm": 1, "rename": 0, "respec": 0}
    assert rs["reviewer_ids"] == [user.id]
    assert rs["edited_items"] == ["Na"]
    assert rs["first_reviewed_at"] and rs["last_reviewed_at"]

    # 문서 내용(원래 값 12, 고친 값 77.7)은 기록에 없다
    dumped = json.dumps({"a": log.approval_summary, "r": log.review_summary}, ensure_ascii=False)
    assert "77.7" not in dumped and '"12"' not in dumped and "오타 수정" not in dumped


def test_cancel_then_delete_keeps_both_approval_rows(auth_client, make_doc, admin, db):
    doc_id = make_doc()
    auth_client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept", "reason": None})
    auth_client.login_as(admin)
    auth_client.post(f"/api/v1/documents/{doc_id}/cancel-approval", json={"reason": "처분 오류"})

    assert delete(auth_client, doc_id, reason="잘못 처분한 문서 정리").status_code == 200

    log = db.scalar(select(DeletionLog))
    assert [(a["action"], a["decision"], a["reason"]) for a in log.approval_summary] == [
        ("approve", "accept", None), ("cancel", None, "처분 오류")]
    assert log.deleted_by == admin.id


def test_failed_delete_writes_no_log(auth_client, make_doc, admin, db):
    """처분 완료 문서는 여전히 409 이고 기록도 남지 않는다."""
    doc_id = make_doc()
    auth_client.post(f"/api/v1/documents/{doc_id}/approve", json={"decision": "accept", "reason": None})
    r = delete(auth_client, doc_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_APPROVED"
    assert db.scalar(select(func.count()).select_from(DeletionLog)) == 0


def test_list_logs_admin_only(auth_client, make_doc, admin):
    doc_id = make_doc()
    delete(auth_client, doc_id)
    r = auth_client.get(LOGS)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

    auth_client.login_as(admin)
    data = auth_client.get(LOGS).json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["document_id"] == doc_id and item["reason"] == "잘못 올린 문서" and item["rule"] == "manual"


def test_list_logs_newest_first_paging_filter(auth_client, make_doc, admin, db):
    ids = [make_doc() for _ in range(3)]
    for i, doc_id in enumerate(ids):
        delete(auth_client, doc_id, reason=f"사유 {i}")
    auth_client.login_as(admin)

    page1 = auth_client.get(LOGS, params={"size": 2}).json()["data"]
    assert page1["total"] == 3
    assert [i["reason"] for i in page1["items"]] == ["사유 2", "사유 1"]
    page2 = auth_client.get(LOGS, params={"size": 2, "page": 2}).json()["data"]
    assert [i["reason"] for i in page2["items"]] == ["사유 0"]

    only = auth_client.get(LOGS, params={"document_id": ids[1]}).json()["data"]
    assert only["total"] == 1 and only["items"][0]["reason"] == "사유 1"
    assert auth_client.get(LOGS, params={"lot_no": "없는로트"}).json()["data"]["total"] == 0


def test_no_delete_api_for_logs(auth_client, admin):
    auth_client.login_as(admin)
    assert auth_client.request("DELETE", f"{LOGS}/1").status_code in (404, 405)
