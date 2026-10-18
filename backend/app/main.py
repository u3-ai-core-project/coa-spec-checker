"""[담당: 공통(장수민 생성, 둘 다 수정)] FastAPI 앱 진입점. 실행: uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.response import ok
from app.services.judgement.cross_rules import validate_rule_names
from app.services.judgement.policy import default_policy

# 판정 정책 설정(.env)이 잘못됐으면 요청을 받기 전에 앱 시작 단계에서 바로 알린다 (ValueError)
validate_rule_names(default_policy().cross_rules)

app = FastAPI(title="CoA 검수 시스템 API", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # 엑셀 리포트 파일명
)

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health", tags=["health"])
def health():
    return ok({"status": "ok"})
