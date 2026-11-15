"""[담당: 장수민] GET /mappings, GET /mappings/conversions, DELETE /mappings/{id} (명세 v1.4 4.23, 화면 5-2)

규칙은 mapping_service 에 있다. 권한: 조회는 USER·ADMIN, 삭제는 ADMIN (require_admin, 홍채령 구현).
등록 API 는 두지 않는다 (매핑은 검수 화면의 항목명 수정으로 쌓인다).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.mapping import ConversionsOut, MappingDeleted, MappingOut
from app.services import mapping_service

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get("", response_model=ApiResponse[list[MappingOut]])
def list_mappings(
    material_code: str | None = Query(None, description="원자재 (예: LI2CO3)"),
    normalized_name: str | None = Query(None, description="사내 표준 항목명 (예: 순도)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """매핑 사전 목록 (협력사 항목명 → 사내 표준 항목명)."""
    return ok(mapping_service.list_mappings(db, material_code=material_code, normalized_name=normalized_name))


@router.get("/conversions", response_model=ApiResponse[ConversionsOut])
def get_conversions(_: User = Depends(get_current_user)):
    """단위·산화물 환산표 (서버 설정값, 조회 전용)."""
    return ok(mapping_service.conversions())


@router.delete("/{mapping_id}", response_model=ApiResponse[MappingDeleted])
def delete_mapping(mapping_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """매핑 삭제 (관리자). 다음 업로드 문서부터 그 표기는 사전 없이 추정한다."""
    return ok(MappingDeleted(id=mapping_service.delete_mapping(db, mapping_id)))
