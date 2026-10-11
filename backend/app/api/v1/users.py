"""[담당: 홍채령] GET /users (명세 4.3)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.user import UserSummary
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=ApiResponse[list[UserSummary]])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """대시보드 관리자 뷰의 담당자 필터 목록."""
    return ok([UserSummary.model_validate(u) for u in user_service.list_users(db)])
