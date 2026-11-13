"""[담당: 장수민] 문서 업로드 검증·저장, 목록·상세 조회 (명세 4.4~4.7). 문서 삭제 (홍채령 추가), 재처리·멈춘 문서 정리."""
import logging
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.enums import DeletionRule, DocumentStatus, ErrorKind, FailStage, LotRecommendation, Role
from app.core.errors import AppException, ErrorCode
from app.models import Document, User
from app.schemas.document import DocumentDetail, DocumentListItem
from app.schemas.extraction import Summary
from app.services import deletion_service, reissue_service, spec_service

logger = logging.getLogger(__name__)

# 파일 앞부분 시그니처로 형식을 확인한다. 확장자만 바꾼 파일을 막기 위해서다.
_SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
_EXTENSIONS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


# ---------------------------------------------------------------------------
# 업로드
# ---------------------------------------------------------------------------
def detect_content_type(file_name: str, head: bytes) -> str:
    """확장자와 실제 내용이 모두 PDF/PNG/JPG 이어야 통과. 아니면 INVALID_FILE."""
    expected = _EXTENSIONS.get(Path(file_name).suffix.lower())
    if expected is None:
        raise AppException(ErrorCode.INVALID_FILE, "PDF, PNG, JPG 파일만 업로드할 수 있습니다")
    if not head.startswith(_SIGNATURES[expected]):
        raise AppException(ErrorCode.INVALID_FILE, "파일 내용이 확장자와 맞지 않거나 손상된 파일입니다")
    return expected


def create_document(
    db: Session,
    *,
    user: User,
    file_name: str,
    content: bytes,
    material_code: str,
    supplier: str | None,
    received_lot_no: str | None,
    spec_set_code: str | None = None,
    batch_id: str | None = None,
) -> Document:
    """파일을 검증·저장하고 queued 상태로 등록한다. commit 까지 한다. batch_id 는 일괄 접수(UC01)일 때만."""
    if not content:
        raise AppException(ErrorCode.INVALID_FILE, "빈 파일입니다")
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppException(ErrorCode.INVALID_FILE, f"{settings.MAX_UPLOAD_MB}MB 이하 파일만 업로드할 수 있습니다")
    content_type = detect_content_type(file_name, content[:16])

    material_code = material_code.strip()
    # 판정에 쓸 규격 세트를 업로드 시점에 정해 문서에 남긴다 (지정 없으면 원자재 기본 세트)
    spec_set = spec_service.resolve_spec_set(db, material_code, (spec_set_code or "").strip() or None)

    doc = Document(
        file_name=file_name,
        file_path="",
        file_size=len(content),
        content_type=content_type,
        material_code=material_code,
        material_name=spec_set.material_name,
        spec_set_id=spec_set.id,
        supplier=(supplier or "").strip() or None,
        received_lot_no=(received_lot_no or "").strip() or None,
        batch_id=batch_id,
        status=DocumentStatus.QUEUED,
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()  # id 확정

    # 저장 파일 이름은 문서 ID. 원래 이름은 file_name 컬럼에 둔다 (한글·중복 이름 문제 회피)
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{doc.id}{Path(file_name).suffix.lower()}"
    path.write_bytes(content)
    doc.file_path = str(path)

    try:
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return doc


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------
def get_document(db: Session, document_id: str) -> Document:
    doc = db.get(
        Document, document_id,
        options=[joinedload(Document.uploader), joinedload(Document.approver), joinedload(Document.extraction),
                 joinedload(Document.spec_set)],
    )
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    return doc


# ---------------------------------------------------------------------------
# 삭제
# ---------------------------------------------------------------------------
def delete_document(db: Session, document_id: str, user: User, reason: str | None) -> str:
    """DELETE /documents/{id}. 삭제 기록을 남기고 문서와 딸린 기록, 원본 파일을 지운다. commit 까지 한다.

    - 권한: 올린 사람 본인 또는 ADMIN. 아니면 403 FORBIDDEN
    - 삭제 사유 필수 (2~500자). 없으면 400 REASON_REQUIRED
    - 처분 완료(approved) 문서는 409 ALREADY_APPROVED (운영 정책 1장: 처분 문서는 보관 기간 동안 삭제하지 않는다)
    - 추출 중(processing) 문서는 409 NOT_READY. 작업이 끝난 뒤(extracted 또는 failed) 지운다
    - 처분 취소된 문서처럼 처분·검수 이력이 있어도 지울 수 있다. 삭제 직전 이력 요약이 deletion_logs 에 남는다
    - 추출 결과·검수 이력·처분 이력·재발행 기준 버전 선택 기록은 DB 의 ON DELETE CASCADE 로 함께 지워진다.
      일괄 접수 입고 건(receipts)은 남고 document_id 만 비워져 "CoA 미접수"로 돌아간다 (ON DELETE SET NULL)
    """
    doc = get_document(db, document_id)
    if user.role != Role.ADMIN and doc.uploaded_by != user.id:
        raise AppException(ErrorCode.FORBIDDEN, "본인이 올린 문서만 삭제할 수 있습니다")
    if doc.status == DocumentStatus.APPROVED:
        raise AppException(ErrorCode.ALREADY_APPROVED, "처분 완료 문서는 삭제할 수 없습니다")
    if doc.status == DocumentStatus.PROCESSING:
        raise AppException(ErrorCode.NOT_READY, "추출 중인 문서는 삭제할 수 없습니다")
    reason = deletion_service.clean_reason(reason)

    _, path = deletion_service.delete_with_log(db, doc, actor_id=user.id, reason=reason, rule=DeletionRule.MANUAL)
    db.commit()
    # 파일은 DB 삭제가 성공한 뒤에 지운다
    deletion_service.remove_file(path)
    return document_id


# ---------------------------------------------------------------------------
# 재처리
# ---------------------------------------------------------------------------
MSG_INTERRUPTED = "서버가 재시작되어 추출이 중단되었습니다. 다시 처리해 주세요"


def retry_document(db: Session, document_id: str, user: User) -> Document:
    """POST /documents/{id}/retry. 추출에 실패한(failed) 문서를 queued 로 되돌린다. commit 까지 한다.

    추출을 다시 시작하는 일(process_document 등록)은 호출한 쪽(라우터)에서 한다.
    - 권한: 올린 사람 본인 또는 ADMIN. 아니면 403 FORBIDDEN (삭제와 같은 규칙)
    - failed 가 아니면 409 NOT_FAILED. 추출 중·대기 중 문서는 이미 처리 중이므로 다시 처리하지 않는다
    - 원본 파일이 없으면 404 DOCUMENT_NOT_FOUND
    """
    doc = get_document(db, document_id)
    if user.role != Role.ADMIN and doc.uploaded_by != user.id:
        raise AppException(ErrorCode.FORBIDDEN, "본인이 올린 문서만 다시 처리할 수 있습니다")
    if doc.status != DocumentStatus.FAILED:
        raise AppException(ErrorCode.NOT_FAILED)
    get_file_path(doc)

    # failed 일 때만 바꾼다. 거의 동시에 두 번 눌러도 한 번만 대기열에 들어간다
    claimed = db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.status == DocumentStatus.FAILED)
        .values(status=DocumentStatus.QUEUED, error_message=None, attempt_count=0, failed_stage=None, error_kind=None)
    )
    if claimed.rowcount == 0:
        db.rollback()
        raise AppException(ErrorCode.NOT_FAILED)
    db.commit()
    db.refresh(doc)
    return doc


def list_resumable_documents(db: Session, max_attempts: int) -> list[str]:
    """서버 시작 때 자동으로 다시 시작할 수 있는 문서 ID. 대기·처리 중이면서 시도 횟수가 상한보다 적은 문서."""
    return list(db.scalars(
        select(Document.id)
        .where(Document.status.in_([DocumentStatus.QUEUED, DocumentStatus.PROCESSING]),
               Document.attempt_count < max_attempts)
        .order_by(Document.uploaded_at, Document.id)
    ))


def recover_stuck_documents(db: Session, *, max_attempts: int | None = None) -> int:
    """서버 시작 시 호출. 대기·처리 중으로 남은 문서를 정리하고, failed 로 바꾼 건수를 돌려준다. commit 까지 한다.

    추출은 서버 안의 백그라운드 작업이라 서버가 꺼지면 사라진다. 그대로 두면 문서가 영원히 대기·처리 중으로 남아
    삭제할 수도(처리 중 문서는 삭제 불가), 다시 처리할 수도 없다.
    - max_attempts 가 없으면 (1단계) 모두 failed 로 바꾼다. 실패 단계는 interrupted, 오류 종류는 일시 오류로 기록한다
    - max_attempts 가 있으면 (2단계) 시도 횟수가 상한보다 적은 문서는 queued 로 되돌려 다시 시작할 수 있게 하고(건수에 안 셈),
      나머지만 failed 로 바꾼다. 문제 있는 문서가 서버를 켤 때마다 반복되는 것을 막는다
    서버 1개(프로세스 1개)로 돌린다는 전제다. 여러 개를 동시에 띄우면 다른 서버가 처리 중인 문서도 정리된다.
    """
    stuck = [DocumentStatus.QUEUED, DocumentStatus.PROCESSING]
    if max_attempts is not None:
        db.execute(update(Document).where(Document.status.in_(stuck), Document.attempt_count < max_attempts)
                   .values(status=DocumentStatus.QUEUED))
        stuck_where = Document.attempt_count >= max_attempts
    else:
        stuck_where = Document.attempt_count >= 0
    result = db.execute(
        update(Document)
        .where(Document.status.in_(stuck), stuck_where)
        .values(status=DocumentStatus.FAILED, error_message=MSG_INTERRUPTED,
                failed_stage=FailStage.INTERRUPTED.value, error_kind=ErrorKind.TRANSIENT,
                processing_finished_at=func.now())
    )
    db.commit()
    return result.rowcount


def get_file_path(doc: Document) -> Path:
    path = Path(doc.file_path)
    if not path.is_file():
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND, "원본 파일을 찾을 수 없습니다")
    return path


def _summary(doc: Document) -> Summary | None:
    if doc.extraction is None:
        return None
    return Summary.model_validate(doc.extraction.result.get("summary"))


def to_list_item(doc: Document) -> DocumentListItem:
    return DocumentListItem(
        document_id=doc.id,
        file_name=doc.file_name,
        file_size=doc.file_size,
        supplier=doc.supplier,
        material_name=doc.material_name,
        lot_no=doc.lot_no,
        status=doc.status,
        lot_recommendation=doc.lot_recommendation,
        final_decision=doc.final_decision,
        summary=_summary(doc),
        uploaded_by=doc.uploader.name,
        uploaded_at=doc.uploaded_at,
        approved_by=doc.approver.name if doc.approver else None,
        approved_at=doc.approved_at,
        error_message=doc.error_message,
        attempt_count=doc.attempt_count,
        failed_stage=doc.failed_stage,
        error_kind=doc.error_kind,
    )


def to_detail(db: Session, doc: Document) -> DocumentDetail:
    # 세트가 연결되지 않은 옛 문서는 원자재 기본 세트 정보를 보여준다
    spec_set = doc.spec_set or spec_service.get_default_set(db, doc.material_code)
    lot_nos = (doc.extraction.result.get("lot_nos") or []) if doc.extraction else []
    return DocumentDetail(
        document_id=doc.id,
        file_name=doc.file_name,
        supplier=doc.supplier,
        material_code=doc.material_code,
        material_name=doc.material_name,
        po_no=doc.po_no,
        lot_no=doc.lot_no,
        lot_nos=lot_nos,
        is_multi_lot=len(lot_nos) >= 2,
        received_lot_no=doc.received_lot_no,
        test_date=doc.test_date,
        origin=doc.origin,
        applied_standard=doc.applied_standard,
        spec_grade=spec_set.grade if spec_set else None,
        spec_set_code=spec_set.code if spec_set else None,
        spec_version=spec_set.version if spec_set else None,
        batch_id=doc.batch_id,
        reissue_status=reissue_service.status_of(db, doc),
        status=doc.status,
        lot_recommendation=doc.lot_recommendation,
        final_decision=doc.final_decision,
        decision_reason=doc.decision_reason,
        error_message=doc.error_message,
        attempt_count=doc.attempt_count,
        failed_stage=doc.failed_stage,
        error_kind=doc.error_kind,
        uploaded_by=doc.uploader.name,
        uploaded_at=doc.uploaded_at,
        approved_by=doc.approver.name if doc.approver else None,
        approved_at=doc.approved_at,
    )


def parse_status_filter(value: str | None) -> list[DocumentStatus] | None:
    """'extracted,in_review,on_hold' → [DocumentStatus...]. 잘못된 값이면 VALIDATION_ERROR."""
    if not value:
        return None
    try:
        return [DocumentStatus(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError:
        allowed = ", ".join(s.value for s in DocumentStatus)
        raise AppException(ErrorCode.VALIDATION_ERROR, f"status: {allowed} 중에서 지정해야 합니다") from None


def list_documents(
    db: Session,
    *,
    statuses: list[DocumentStatus] | None,
    lot_recommendation: LotRecommendation | None,
    uploaded_by: int | None,
    page: int,
    size: int,
    batch_id: str | None = None,
) -> tuple[int, list[Document]]:
    """최근 업로드 순. 검수 화면의 이전/다음 이동도 이 순서를 따른다 (명세 4.5)."""
    conditions = []
    if statuses:
        conditions.append(Document.status.in_(statuses))
    if lot_recommendation:
        conditions.append(Document.lot_recommendation == lot_recommendation)
    if uploaded_by is not None:
        conditions.append(Document.uploaded_by == uploaded_by)
    if batch_id:
        conditions.append(Document.batch_id == batch_id)

    total = db.scalar(select(func.count()).select_from(Document).where(*conditions))
    rows = db.scalars(
        select(Document)
        .where(*conditions)
        .options(joinedload(Document.uploader), joinedload(Document.approver), joinedload(Document.extraction))
        .order_by(Document.uploaded_at.desc(), Document.id)
        .offset((page - 1) * size)
        .limit(size)
    ).unique()
    return total, list(rows)
