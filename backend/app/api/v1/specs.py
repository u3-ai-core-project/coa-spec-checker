"""[담당: 장수민] GET /specs, GET /specs/sets, PATCH /specs/{id}, GET /specs/{id}/change-logs (명세 4.20, 4.21, v1.4)

규칙은 spec_service 에 있다. 권한: 조회는 USER·ADMIN, 수정은 ADMIN (require_admin, 홍채령 구현).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.spec import SpecChangeLogOut, SpecItemOut, SpecSetOut, SpecUpdateOut, SpecUpdateRequest
from app.services import spec_service

router = APIRouter(prefix="/specs", tags=["specs"])


@router.get("", response_model=ApiResponse[list[SpecItemOut]])
def list_specs(
    material_code: str | None = Query(None, description="원자재 (예: LI2CO3)"),
    spec_set_code: str | None = Query(None, description="규격 세트 (v1.4안, 예: LI2CO3-D1-2023)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """사내 규격 항목 목록. 항목마다 세트 코드·버전·필수 여부가 함께 나간다."""
    return ok(spec_service.list_items(db, material_code=material_code, spec_set_code=spec_set_code))


@router.get("/sets", response_model=ApiResponse[list[SpecSetOut]])
def list_spec_sets(
    material_code: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """규격 세트 목록 (v1.4안, 명세 외 추가). 업로드 화면의 원자재·규격 선택지로 쓴다."""
    return ok(spec_service.list_set_summaries(db, material_code))


@router.patch("/{spec_id}", response_model=ApiResponse[SpecUpdateOut])
def update_spec(spec_id: int, body: SpecUpdateRequest, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    """규격 항목 수정 (관리자). 변경 사유 필수. 기본은 이후 업로드되는 문서부터 적용, rejudge=true 면 처분 전 문서도 다시 판정."""
    return ok(spec_service.update_item(db, spec_id, body, user))


@router.get("/{spec_id}/change-logs", response_model=ApiResponse[list[SpecChangeLogOut]])
def list_change_logs(spec_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """규격 변경 이력 (v1.4). 오래된 순."""
    return ok(spec_service.list_change_logs(db, spec_id))
