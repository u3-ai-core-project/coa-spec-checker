"""[담당: 공통(장수민 생성, 둘 다 수정)] FastAPI 앱 진입점. 실행: uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.response import ok
from app.db.session import SessionLocal
from app.services import document_service
from app.services.judgement.cross_rules import validate_rule_names
from app.services.judgement.policy import default_policy

logger = logging.getLogger(__name__)

# 판정 정책 설정(.env)이 잘못됐으면 요청을 받기 전에 앱 시작 단계에서 바로 알린다 (ValueError)
validate_rule_names(default_policy().cross_rules)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 서버가 꺼질 때 추출 중이던 문서를 실패로 정리한다. DB 에 연결하지 못해도 서버는 뜬다
    try:
        with SessionLocal() as db:
            stuck = document_service.recover_stuck_documents(db)
        if stuck:
            logger.warning("서버가 꺼지면서 멈춘 문서 %d건을 실패로 정리했습니다", stuck)
    except Exception:
        logger.exception("멈춘 문서 정리에 실패했습니다")
    yield


app = FastAPI(title="CoA 검수 시스템 API", version="1.3.0", lifespan=lifespan)

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
