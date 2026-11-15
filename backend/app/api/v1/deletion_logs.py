"""[담당: 홍채령] GET /deletion-logs — 문서 삭제 기록 조회 (운영 정책 1장, ADMIN 전용, 명세 추가 예정).

삭제 기록은 조회만 한다. 지우거나 고치는 API 는 두지 않는다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse, Page
from app.schemas.deletion_log import DeletionLogItem
from app.services import deletion_service

router = APIRouter(prefix="/deletion-logs", tags=["deletion-logs"])


@router.get("", response_model=ApiResponse[Page[DeletionLogItem]])
def list_deletion_logs(
    document_id: str | None = Query(None, description="지운 문서 ID"),
    lot_no: str | None = Query(None, description="CoA 로트번호 (정확히 일치)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """최근 삭제부터."""
    total, items = deletion_service.list_logs(db, document_id=document_id, lot_no=lot_no, page=page, size=size)
    return ok(Page(total=total, items=[DeletionLogItem.model_validate(i) for i in items]))
