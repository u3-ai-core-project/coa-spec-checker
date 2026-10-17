"""[담당: 장수민] 문서 업로드 검증·저장, 목록·상세 조회 (명세 4.4~4.7)."""
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.enums import DocumentStatus, LotRecommendation
from app.core.errors import AppException, ErrorCode
from app.models import Document, User
from app.schemas.document import DocumentDetail, DocumentListItem
from app.schemas.extraction import Summary
from app.services import spec_service

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
) -> Document:
    """파일을 검증·저장하고 queued 상태로 등록한다. commit 까지 한다."""
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
    )


def to_detail(db: Session, doc: Document) -> DocumentDetail:
    # 세트가 연결되지 않은 옛 문서는 원자재 기본 세트 정보를 보여준다
    spec_set = doc.spec_set or spec_service.get_default_set(db, doc.material_code)
    return DocumentDetail(
        document_id=doc.id,
        file_name=doc.file_name,
        supplier=doc.supplier,
        material_code=doc.material_code,
        material_name=doc.material_name,
        po_no=doc.po_no,
        lot_no=doc.lot_no,
        received_lot_no=doc.received_lot_no,
        test_date=doc.test_date,
        origin=doc.origin,
        applied_standard=doc.applied_standard,
        spec_grade=spec_set.grade if spec_set else None,
        spec_set_code=spec_set.code if spec_set else None,
        spec_version=spec_set.version if spec_set else None,
        status=doc.status,
        lot_recommendation=doc.lot_recommendation,
        final_decision=doc.final_decision,
        decision_reason=doc.decision_reason,
        error_message=doc.error_message,
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
) -> tuple[int, list[Document]]:
    """최근 업로드 순. 검수 화면의 이전/다음 이동도 이 순서를 따른다 (명세 4.5)."""
    conditions = []
    if statuses:
        conditions.append(Document.status.in_(statuses))
    if lot_recommendation:
        conditions.append(Document.lot_recommendation == lot_recommendation)
    if uploaded_by is not None:
        conditions.append(Document.uploaded_by == uploaded_by)

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
