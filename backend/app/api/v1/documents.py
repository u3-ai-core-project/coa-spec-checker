"""[담당: 장수민] POST /documents, GET /documents, GET /documents/{id}, GET /documents/{id}/file (명세 4.4~4.7)
일괄 접수: POST /documents/batch, GET /documents/batch/{batch_id} (명세 v1.4 4.4-1, 4.4-2, 멘토님 UC01)
문서 삭제: DELETE /documents/{id} (홍채령 추가, 명세 추가 예정)
문서 재처리: POST /documents/{id}/retry (명세 추가 예정)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.enums import LotRecommendation
from app.core.errors import AppException, ErrorCode
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.pipeline.worker import process_document
from app.schemas.common import ApiResponse, Page
from app.schemas.batch import BatchDetail, BatchUploadResponse
from app.schemas.document import DocumentDeleteRequest, DocumentDeleted, DocumentDetail, DocumentListItem, DocumentUploadResponse
from app.services import batch_service, document_service

router = APIRouter(prefix="/documents", tags=["documents"])

_CHUNK_SIZE = 1024 * 1024  # 1MB 씩 나눠 읽는다


def _too_large_message() -> str:
    return f"{settings.MAX_UPLOAD_MB}MB 이하 파일만 업로드할 수 있습니다"


def _batch_total_limit() -> int:
    """일괄 접수 전체 합계 상한 (바이트): 파일 하나 상한 × 최대 파일 수."""
    return settings.MAX_UPLOAD_MB * 1024 * 1024 * settings.MAX_BATCH_FILES


async def _read_limited(file: UploadFile, limit: int, *, message: str) -> bytes:
    """파일을 1MB 씩 읽다가 limit 바이트를 넘는 순간 INVALID_FILE 로 멈춘다.

    한 번에 file.read() 하면 아주 큰 파일도 통째로 메모리에 올라간다. 나눠 읽으면 상한을 넘는 즉시 끊을 수 있다.
    """
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK_SIZE):
        size += len(chunk)
        if size > limit:
            raise AppException(ErrorCode.INVALID_FILE, message)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[DocumentUploadResponse])
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, PNG, JPG"),
    material_code: str = Form(..., description="원자재 구분 (예: LI2CO3)"),
    supplier: str | None = Form(None, description="협력사명"),
    received_lot_no: str | None = Form(None, description="입고 로트번호 (확장)"),
    spec_set_code: str | None = Form(None, description="사내 규격 세트 (v1.4안, 예: LI2CO3-D1-2023). 없으면 원자재 기본 세트"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content = await _read_limited(file, settings.MAX_UPLOAD_MB * 1024 * 1024, message=_too_large_message())
    doc = document_service.create_document(
        db,
        user=user,
        file_name=file.filename or "upload",
        content=content,
        material_code=material_code,
        supplier=supplier,
        received_lot_no=received_lot_no,
        spec_set_code=spec_set_code,
    )
    background_tasks.add_task(process_document, doc.id)
    return ok(DocumentUploadResponse(document_id=doc.id, file_name=doc.file_name, status=doc.status))


@router.post("/batch", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[BatchUploadResponse])
async def upload_batch(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="CoA 파일 1~20개 (PDF, PNG, JPG)"),
    material_code: str = Form(..., description="원자재 구분 (입고 CSV 에 material 이 없는 행과 연결되지 않은 파일에 적용)"),
    spec_set_code: str | None = Form(None, description="기본 사내 규격 세트. 입고 CSV 의 spec_id 가 있으면 그것을 우선"),
    receipts: UploadFile | None = File(None, description="입고 정보 CSV (receipt_id, received_lot 필수)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 파일 수는 읽기 전에 먼저 본다 (batch_service 에도 같은 검사가 있다). 너무 많은 파일을 메모리에 올리지 않기 위해서다
    if len(files) > settings.MAX_BATCH_FILES:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"한 번에 {settings.MAX_BATCH_FILES}개까지 올릴 수 있습니다")
    per_file = settings.MAX_UPLOAD_MB * 1024 * 1024
    # 전체 합계 상한: 파일 하나 상한 × 최대 파일 수. 위 두 검사로 보통은 넘을 수 없지만, 설정이 바뀌어도 지키도록 남겨 둔다
    total_limit = _batch_total_limit()
    remaining = total_limit
    total_message = f"한 번에 올리는 파일의 합계는 {total_limit // (1024 * 1024)}MB 이하여야 합니다"
    uploads = []
    for f in files:
        # 남은 합계 한도가 파일 하나 상한보다 작으면 합계 한도로 끊는다
        limit, message = (per_file, _too_large_message()) if remaining >= per_file else (remaining, total_message)
        content = await _read_limited(f, limit, message=message)
        remaining -= len(content)
        uploads.append(batch_service.UploadFile(name=f.filename or "upload", content=content))
    receipts_csv = (
        await _read_limited(receipts, per_file, message=f"입고 정보 CSV 는 {_too_large_message()}")
        if receipts is not None else None
    )
    created = batch_service.create_batch(
        db, user=user, files=uploads, material_code=material_code, spec_set_code=spec_set_code,
        receipts_csv=receipts_csv,
    )
    for doc, _ in created.documents:
        background_tasks.add_task(process_document, doc.id)
    return ok(batch_service.to_upload_response(created))


@router.get("/batch/{batch_id}", response_model=ApiResponse[BatchDetail])
def get_batch(batch_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return ok(batch_service.get_batch(db, batch_id))


@router.get("", response_model=ApiResponse[Page[DocumentListItem]])
def list_documents(
    status_: str | None = Query(None, alias="status", description="쉼표로 여러 개 (예: extracted,in_review,on_hold)"),
    lot_recommendation: LotRecommendation | None = Query(None),
    uploaded_by: int | None = Query(None, description="업로드한 사용자 id"),
    batch_id: str | None = Query(None, description="일괄 접수 묶음 ID (v1.4)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total, docs = document_service.list_documents(
        db,
        statuses=document_service.parse_status_filter(status_),
        lot_recommendation=lot_recommendation,
        uploaded_by=uploaded_by,
        batch_id=batch_id,
        page=page,
        size=size,
    )
    return ok(Page(total=total, items=[document_service.to_list_item(d) for d in docs]))


@router.get("/{document_id}", response_model=ApiResponse[DocumentDetail])
def get_document(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = document_service.get_document(db, document_id)
    return ok(document_service.to_detail(db, doc))


@router.get(
    "/{document_id}/file",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}, "image/png": {}, "image/jpeg": {}}}},
)
def get_document_file(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = document_service.get_document(db, document_id)
    return FileResponse(
        document_service.get_file_path(doc),
        media_type=doc.content_type,
        filename=doc.file_name,
        content_disposition_type="inline",  # 브라우저·PDF 뷰어에서 바로 열리도록
    )


@router.delete("/{document_id}", response_model=ApiResponse[DocumentDeleted])
def delete_document(document_id: str, body: DocumentDeleteRequest | None = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """문서 삭제. 올린 사람 본인 또는 ADMIN. 본문 {reason} 필수. 처분 완료·추출 중 문서는 지울 수 없다.

    삭제 기록(누가, 언제, 무엇을, 왜 + 처분·검수 이력 요약)이 남는다 (운영 정책 1장, GET /deletion-logs).
    """
    deleted_id = document_service.delete_document(db, document_id, user, body.reason if body else None)
    return ok(DocumentDeleted(document_id=deleted_id))


@router.post("/{document_id}/retry", response_model=ApiResponse[DocumentUploadResponse])
def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """추출에 실패한(failed) 문서를 다시 처리한다. 올린 사람 본인 또는 ADMIN. 응답 상태는 queued."""
    doc = document_service.retry_document(db, document_id, user)
    background_tasks.add_task(process_document, doc.id)
    return ok(DocumentUploadResponse(document_id=doc.id, file_name=doc.file_name, status=doc.status))
