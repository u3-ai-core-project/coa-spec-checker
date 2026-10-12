"""[담당: 공통] v1 라우터 묶음. 모든 라우터를 미리 등록해 두어 이 파일은 더 고칠 일이 없게 한다."""
from fastapi import APIRouter

from app.api.v1 import anomalies, approval, auth, dashboard, documents, extraction, reports, specs, users

api_router = APIRouter(prefix="/api/v1")

for module in (auth, users, documents, extraction, approval, reports, anomalies, dashboard, specs):
    api_router.include_router(module.router)
