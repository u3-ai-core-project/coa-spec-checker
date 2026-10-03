"""[담당: 장수민] POST /documents, GET /documents, GET /documents/{id}, GET /documents/{id}/file (명세 4.4~4.7)

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
from app.schemas.document import DocumentDetail, DocumentListItem, DocumentUploadResponse
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[DocumentUploadResponse])
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, PNG, JPG"),
    material_code: str = Form(..., description="원자재 구분 (예: LI2CO3)"),
    supplier: str | None = Form(None, description="협력사명"),
    received_lot_no: str | None = Form(None, description="입고 로트번호 (확장)"),
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
    )
    background_tasks.add_task(process_document, doc.id)
    return ok(DocumentUploadResponse(document_id=doc.id, file_name=doc.file_name, status=doc.status))


@router.get("", response_model=ApiResponse[Page[DocumentListItem]])
def list_documents(
    status_: str | None = Query(None, alias="status", description="쉼표로 여러 개 (예: extracted,in_review,on_hold)"),
    lot_recommendation: LotRecommendation | None = Query(None),
    uploaded_by: int | None = Query(None, description="업로드한 사용자 id"),
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
