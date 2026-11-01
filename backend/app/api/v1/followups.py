"""[담당: 장수민] GET /documents/{id}/follow-ups (명세 v1.4안 4.22)

검수 화면의 예외 상세 패널(UI 2-11: 왜 문제인가 / 해결 조건 / 문의 초안)과
배치 화면의 공급사별 문의 묶음(UI 3-5)에 쓴다. 규칙은 followup_service 에 있다.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.schemas.followup import FollowUpsResponse
from app.services import followup_service

router = APIRouter(prefix="/documents", tags=["follow-ups"])


@router.get("/{document_id}/follow-ups", response_model=ApiResponse[FollowUpsResponse])
def get_follow_ups(
    document_id: str,
    draft: Literal["ai", "template"] | None = Query(
        None, description="ai 면 AI 초안(\"AI로 다듬기\"), template 이면 템플릿. 없으면 서버 설정(기본 템플릿)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """후속 조치 목록, 보류 후속 조치 추천, 공급사 문의 초안 (같은 공급사 열린 요청 묶음 포함)."""
    return ok(followup_service.get_follow_ups(db, document_id, draft))
