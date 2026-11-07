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
from app.core.enums import LotRecommendation
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.pipeline.worker import process_document
from app.schemas.common import ApiResponse, Page
from app.schemas.batch import BatchDetail, BatchUploadResponse
from app.schemas.document import DocumentDeleted, DocumentDetail, DocumentListItem, DocumentUploadResponse
from app.services import batch_service, document_service

router = APIRouter(prefix="/documents", tags=["documents"])


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
    content = await file.read()
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
    uploads = [batch_service.UploadFile(name=f.filename or "upload", content=await f.read()) for f in files]
    created = batch_service.create_batch(
        db, user=user, files=uploads, material_code=material_code, spec_set_code=spec_set_code,
        receipts_csv=await receipts.read() if receipts is not None else None,
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
def delete_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """문서 삭제. 올린 사람 본인 또는 ADMIN. 처분 완료·추출 중 문서는 지울 수 없다."""
    deleted_id = document_service.delete_document(db, document_id, user)
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
