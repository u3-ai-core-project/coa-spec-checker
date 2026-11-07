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
from app.schemas.dashboard import DashboardSummary, LotTrends
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=ApiResponse[DashboardSummary])
def get_summary(
    scope: Literal["mine", "all"] | None = Query(None, description="USER 기본 mine, ADMIN 기본 all"),
    user_id: int | None = Query(None, description="담당자 필터 (ADMIN 전용)"),
    date_from: date | None = Query(None, alias="from", description="조회 시작일 (YYYY-MM-DD)"),
    date_to: date | None = Query(None, alias="to", description="조회 종료일 (YYYY-MM-DD, 포함)"),
    material_code: str | None = Query(None, description="원자재 구분 (예: LI2CO3)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uploaded_by = dashboard_service.resolve_uploader_filter(user, scope, user_id)
    return ok(dashboard_service.get_summary(db, uploaded_by, date_from, date_to, material_code))


@router.get("/lot-trends", response_model=ApiResponse[LotTrends])
def get_lot_trends(
    item_name: str = Query(..., min_length=1, description="표준 항목명 (4.18 deviation_by_item 의 item_name)"),
    scope: Literal["mine", "all"] | None = Query(None, description="USER 기본 mine, ADMIN 기본 all"),
    user_id: int | None = Query(None, description="담당자 필터 (ADMIN 전용)"),
    date_from: date | None = Query(None, alias="from", description="처분 일시 시작일 (YYYY-MM-DD)"),
    date_to: date | None = Query(None, alias="to", description="처분 일시 종료일 (YYYY-MM-DD, 포함)"),
    material_code: str | None = Query(None, description="원자재 구분 (예: LI2CO3)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """로트별 반복 이탈 항목 추이 (명세 4.19, 확장). 권한·필터는 4.18 요약과 같다."""
    uploaded_by = dashboard_service.resolve_uploader_filter(user, scope, user_id)
    return ok(dashboard_service.get_lot_trends(db, item_name, uploaded_by, date_from, date_to, material_code))
