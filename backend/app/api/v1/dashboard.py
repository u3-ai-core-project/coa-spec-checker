"""[담당: 홍채령] GET /dashboard/summary, GET /dashboard/lot-trends (명세 4.18, 4.19)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=ApiResponse[DashboardSummary])
def get_summary(
    scope: Literal["mine", "all"] | None = Query(None, description="USER 기본 mine, ADMIN 기본 all"),
    user_id: int | None = Query(None, description="담당자 필터 (ADMIN 전용)"),
    date_from: date | None = Query(None, alias="from", description="조회 시작일 (YYYY-MM-DD)"),
    date_to: date | None = Query(None, alias="to", description="조회 종료일 (YYYY-MM-DD, 포함)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uploaded_by = dashboard_service.resolve_uploader_filter(user, scope, user_id)
    return ok(dashboard_service.get_summary(db, uploaded_by, date_from, date_to))
