"""[담당: 공통(장수민 생성, 둘 다 수정)] FastAPI 앱 진입점. 실행: uvicorn app.main:app --reload"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.response import error_body, ok
from sqlalchemy import text

from app.db.session import SessionLocal
from app.pipeline.worker import process_document
from app.services import document_service
from app.services.judgement.cross_rules import validate_rule_names
from app.services.judgement.policy import default_policy

logger = logging.getLogger(__name__)

# 판정 정책 설정(.env)이 잘못됐으면 요청을 받기 전에 앱 시작 단계에서 바로 알린다 (ValueError)
validate_rule_names(default_policy().cross_rules)


def _resume(document_ids: list[str]) -> None:
    for document_id in document_ids:
        process_document(document_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 서버가 꺼질 때 추출 중이던 문서를 정리한다. DB 에 연결하지 못해도 서버는 뜬다
    # RESUME_STUCK_ON_START 가 켜져 있으면 시도 상한 안의 문서는 다시 시작한다 (운영 정책 4장 2단계)
    resume_ids: list[str] = []
    try:
        with SessionLocal() as db:
            if settings.RESUME_STUCK_ON_START:
                resume_ids = document_service.list_resumable_documents(db, settings.MAX_EXTRACTION_ATTEMPTS)
                stuck = document_service.recover_stuck_documents(db, max_attempts=settings.MAX_EXTRACTION_ATTEMPTS)
            else:
                stuck = document_service.recover_stuck_documents(db)
        if stuck:
            logger.warning("서버가 꺼지면서 멈춘 문서 %d건을 실패로 정리했습니다", stuck)
        if resume_ids:
            logger.warning("멈춘 문서 %d건을 다시 시작합니다", len(resume_ids))
    except Exception:
        logger.exception("멈춘 문서 정리에 실패했습니다")
        resume_ids = []
    if resume_ids:
        threading.Thread(target=_resume, args=(resume_ids,), daemon=True).start()
    yield


app = FastAPI(title="CoA 검수 시스템 API", version=__version__, lifespan=lifespan)

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
    """서버와 DB 연결 상태. DB 에 연결하지 못하면 503 (운영 정책 4장)."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("상태 확인: DB 연결 실패")
        return JSONResponse(status_code=503, content=error_body("DB_UNAVAILABLE", "데이터베이스에 연결할 수 없습니다"))
    return ok({"status": "ok", "database": "ok", "version": __version__})
