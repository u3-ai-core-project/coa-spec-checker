"""[담당: 홍채령] 문서 삭제 기록 (운영 정책 1장).

"삭제할 때 누가, 언제, 무엇을, 왜 지웠는지 삭제 기록을 남기고, 삭제 직전의 처분·검수 이력 요약도 함께 저장한다."

delete_with_log() 는 사람 삭제(DELETE /documents/{id})와 나중에 만들 자동 정리·묶음 삭제가 같이 쓴다.
권한·상태 검사는 호출한 쪽에서 하고, 여기서는 "기록 남기기 + 문서 지우기"만 한다.

기록에 문서 내용(추출 값, 수정 전후 값)은 넣지 않는다. 검수 요약은 횟수, 시각, 수정한 항목 이름만이다.
"""
import hashlib
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import DeletionRule, DocumentStatus, ReviewAction
from app.core.errors import AppException, ErrorCode
from app.models import ApprovalLog, DeletionLog, Document, ReviewLog
from app.models.reissue_decision import ReissueDecision
from app.services import storage_service

logger = logging.getLogger(__name__)

REASON_MIN, REASON_MAX = 2, 500


def clean_reason(reason: str | None) -> str:
    """삭제 사유: 앞뒤 공백을 빼고 2~500자. 아니면 400 REASON_REQUIRED (다른 사유 필수 API 와 같은 코드)."""
    text = (reason or "").strip()
    if not text:
        raise AppException(ErrorCode.REASON_REQUIRED, "삭제 사유를 입력해야 합니다")
    if not REASON_MIN <= len(text) <= REASON_MAX:
        raise AppException(ErrorCode.REASON_REQUIRED, f"삭제 사유는 {REASON_MIN}~{REASON_MAX}자로 입력해야 합니다")
    return text


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _file_sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def approval_summary(db: Session, document_id: str) -> list[dict]:
    """처분·보류·취소 이력 전부 (오래된 것부터)."""
    logs = db.scalars(select(ApprovalLog).where(ApprovalLog.document_id == document_id).order_by(ApprovalLog.id))
    return [
        {
            "action": log.action.value,
            "decision": log.decision.value if log.decision else None,
            "follow_up": log.follow_up.value if log.follow_up else None,
            "user_id": log.user_id,
            "at": _iso(log.created_at),
            "reason": log.reason,
        }
        for log in logs
    ]


def review_summary(db: Session, doc: Document) -> dict:
    """검수 이력 요약: 종류별 횟수, 처음·마지막 시각, 값·항목명을 고친 항목 이름. 수정 전후 값은 넣지 않는다."""
    logs = list(db.scalars(select(ReviewLog).where(ReviewLog.document_id == doc.id).order_by(ReviewLog.id)))
    counts = {action.value: 0 for action in ReviewAction}
    for log in logs:
        counts[log.action.value] += 1
    names = {}
    items = (doc.extraction.result.get("items", []) if doc.extraction is not None else []) or []
    for item in items:
        if item.get("item_id"):
            names[item["item_id"]] = item.get("normalized_name") or item.get("raw_name") or item["item_id"]
    changed = [log.item_id for log in logs if log.action in (ReviewAction.EDIT, ReviewAction.RENAME)]
    edited_items = list(dict.fromkeys(names.get(i, i) for i in changed))
    reissue_count = db.scalar(
        select(func.count()).select_from(ReissueDecision).where(ReissueDecision.base_document_id == doc.id)
    )
    return {
        "counts": counts,
        "reviewer_ids": sorted({log.reviewer_id for log in logs}),
        "first_reviewed_at": _iso(logs[0].reviewed_at) if logs else None,
        "last_reviewed_at": _iso(logs[-1].reviewed_at) if logs else None,
        "edited_items": edited_items,
        "reissue_base_selections": reissue_count,  # 이 문서를 기준 버전으로 고른 기록 (문서와 함께 지워짐)
    }


def delete_with_log(db: Session, doc: Document, *, actor_id: int | None, reason: str,
                    rule: DeletionRule) -> tuple[DeletionLog, Path | None]:
    """삭제 기록을 쓰고 문서를 지운다 (같은 트랜잭션). commit 과 원본 파일 삭제는 호출한 쪽에서 한다.

    반환: (삭제 기록, 지워야 할 원본 파일 경로). 파일은 commit 이 성공한 뒤에 remove_file() 로 지운다.
    """
    path = Path(doc.file_path) if doc.file_path else None
    log = DeletionLog(
        document_id=doc.id,
        file_name=doc.file_name,
        file_size=doc.file_size,
        file_sha256=_file_sha256(path) if path is not None else None,
        material_code=doc.material_code,
        supplier=doc.supplier,
        lot_no=doc.lot_no,
        received_lot_no=doc.received_lot_no,
        batch_id=doc.batch_id,
        status_at_delete=doc.status.value if doc.status else None,
        uploaded_by=doc.uploaded_by,
        uploaded_at=doc.uploaded_at,
        deleted_by=actor_id,
        reason=reason,
        rule=rule,
        approval_summary=approval_summary(db, doc.id),
        review_summary=review_summary(db, doc),
    )
    db.add(log)
    db.flush()  # 기록이 먼저 들어가야 한다. 실패하면 문서도 지워지지 않는다
    db.delete(doc)
    return log, path


def remove_file(path: Path | None) -> None:
    """원본 파일 삭제. 실패해도 문서는 이미 없으므로 로그만 남긴다 (경로만, 내용 없음)."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("원본 파일 삭제 실패: %s", path)
    storage_service.invalidate()  # 저장 공간 기억값을 버려 다음에 새로 잰다


def list_logs(db: Session, *, document_id: str | None, lot_no: str | None, page: int, size: int):
    """GET /deletion-logs. 최근 삭제부터. (total, items)."""
    query = select(DeletionLog)
    if document_id:
        query = query.where(DeletionLog.document_id == document_id)
    if lot_no:
        query = query.where(DeletionLog.lot_no == lot_no)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = list(db.scalars(query.order_by(DeletionLog.deleted_at.desc(), DeletionLog.id.desc())
                            .offset((page - 1) * size).limit(size)))
    return total, items


def delete_batch(db: Session, batch_id: str, actor_id: int, reason: str | None) -> dict:
    """DELETE /documents/batch/{batch_id} (ADMIN, 운영 정책 1장). 잘못 올린 일괄 접수 묶음을 통째로 지운다. commit 까지 한다.

    - 묶음 없음: 404 NOT_FOUND
    - 처분 완료(보관 기간) 또는 추출 중 문서가 하나라도 있으면 409 BATCH_NOT_DELETABLE (data.blocking 에 문서 목록). 아무것도 안 지운다
    - 사유 필수 (2~500자, 400 REASON_REQUIRED)
    - 한 트랜잭션: 문서마다 삭제 기록(rule=batch_delete) → 문서 삭제 → 묶음 단위 기록 1줄 → 입고 건·묶음 삭제. 파일은 commit 뒤에 지운다
    """
    from app.models import Batch  # 순환 import 방지
    batch = db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
    if batch is None:
        raise AppException(ErrorCode.NOT_FOUND, "존재하지 않는 일괄 접수입니다")
    docs = list(db.scalars(select(Document).where(Document.batch_id == batch_id)
                           .order_by(Document.uploaded_at, Document.id).with_for_update()))
    blocking = [d for d in docs if d.status in (DocumentStatus.APPROVED, DocumentStatus.PROCESSING)]
    if blocking:
        raise AppException(
            ErrorCode.BATCH_NOT_DELETABLE,
            f"처분 완료되었거나 추출 중인 문서 {len(blocking)}건이 있어 묶음을 삭제할 수 없습니다",
            data={"blocking": [{"document_id": d.id, "file_name": d.file_name, "status": d.status.value}
                               for d in blocking]},
        )
    reason = clean_reason(reason)

    paths = []
    for doc in docs:
        _, path = delete_with_log(db, doc, actor_id=actor_id, reason=reason, rule=DeletionRule.BATCH_DELETE)
        paths.append(path)
    receipt_count = len(batch.receipts)
    # 묶음 단위 기록: 문서가 없는 줄 하나 (document_id 없음, batch_id 있음)
    db.add(DeletionLog(
        document_id=None, file_name="(일괄 접수 묶음)", batch_id=batch.id, material_code=batch.material_code,
        uploaded_by=batch.created_by, uploaded_at=batch.created_at, deleted_by=actor_id, reason=reason,
        rule=DeletionRule.BATCH_DELETE, approval_summary=[],
        review_summary={"batch": {"documents": len(docs), "receipts": receipt_count,
                                  "document_ids": [d.id for d in docs]}},
    ))
    db.delete(batch)  # 입고 건(receipts)도 함께 지워진다
    db.commit()
    for path in paths:
        remove_file(path)
    logger.info("일괄 접수 묶음 삭제: batch_id=%s actor_id=%s 문서 %d건 입고 %d건",
                batch_id, actor_id, len(docs), receipt_count)
    return {"batch_id": batch_id, "deleted_documents": [d.id for d in docs], "deleted_receipts": receipt_count}
