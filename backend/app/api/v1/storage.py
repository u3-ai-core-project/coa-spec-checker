"""[담당: 홍채령] GET /storage — 저장 공간 단계 (운영 정책 1장, 로그인한 모든 사용자, 명세 추가 예정).

업로드 화면에서 "저장 공간이 거의 찼습니다"(warn), "새 업로드를 받을 수 없습니다"(block) 안내를 띄우는 데 쓴다.
사용량 바이트·정리 후보 같은 자세한 내용은 GET /admin/storage (ADMIN).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.response import ok
from app.models import User
from app.schemas.common import ApiResponse
from app.services import storage_service

router = APIRouter(prefix="/storage", tags=["storage"])


class StorageStatus(BaseModel):
    level: str          # ok | warn | block
    reason: str | None  # block 이유: quota(설정 한도) | disk(서버 디스크 실제 남은 공간 부족) | null
    used_percent: float
    warn_percent: int
    block_percent: int


@router.get("", response_model=ApiResponse[StorageStatus])
def storage_status(_: User = Depends(get_current_user)):
    return ok(StorageStatus(**storage_service.public_status()))
