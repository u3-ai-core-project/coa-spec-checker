"""[담당: 홍채령] 관리자 운영 기능 (운영 정책 1장, ADMIN 전용, 명세 추가 예정).

- POST /admin/cleanup/run?dry_run=true|false  자동 정리를 바로 한 번 돌린다 (dry_run 이면 대상만 보여 주고 바꾸지 않음)
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.services import cleanup_service

router = APIRouter(prefix="/admin", tags=["admin"])


class CleanupRunResponse(BaseModel):
    dry_run: bool
    failed_documents_deleted: list[str]  # 지운(dry_run 이면 지울) 실패 문서 ID
    orphan_files_deleted: list[str]      # 지운(지울) 연결 안 된 파일의 저장 이름
    stale_documents_marked: list[str]    # 방치로 표시한(표시할) 문서 ID


@router.post("/cleanup/run", response_model=ApiResponse[CleanupRunResponse])
def run_cleanup(dry_run: bool = Query(False, description="true 면 대상만 보여 주고 아무것도 바꾸지 않는다"),
                db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return ok(CleanupRunResponse(**asdict(cleanup_service.run_cleanup(db, dry_run=dry_run))))
