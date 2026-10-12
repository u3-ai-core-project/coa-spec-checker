"""[담당: 장수민] 에러 코드와 전역 예외 핸들러 (명세 5장).

서비스/라우터에서는 아래처럼만 쓰면 공통 에러 형식으로 응답된다.

    raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    raise AppException(ErrorCode.REASON_REQUIRED, "조건부 승인은 사유가 필요합니다")
"""
import logging
from enum import Enum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import error_body

logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    # (HTTP 상태, 기본 메시지)
    INVALID_FILE = (400, "지원하지 않는 파일 형식이거나 손상된 파일입니다")
    UNKNOWN_MATERIAL = (400, "등록되지 않은 원자재 구분입니다")
    UNKNOWN_ITEM_NAME = (400, "사내 규격에 없는 항목명입니다")
    REASON_REQUIRED = (400, "사유를 입력해야 합니다")
    INVALID_SPEC_RANGE = (400, "규격 하한이 상한보다 큽니다")
    VALIDATION_ERROR = (400, "요청 형식이 올바르지 않습니다")  # 명세 외 추가 (아래 핸들러 참고)
    INVALID_CREDENTIALS = (401, "아이디 또는 비밀번호가 올바르지 않습니다")
    UNAUTHORIZED = (401, "인증이 필요합니다")
    FORBIDDEN = (403, "권한이 없습니다")
    NOT_FOUND = (404, "요청한 경로를 찾을 수 없습니다")  # 명세 외 추가 (없는 URL)
    DOCUMENT_NOT_FOUND = (404, "존재하지 않는 문서입니다")
    ITEM_NOT_FOUND = (404, "문서에 존재하지 않는 항목입니다")
    SPEC_NOT_FOUND = (404, "존재하지 않는 규격 항목입니다")
    ALREADY_APPROVED = (409, "이미 처분된 문서입니다")
    NOT_APPROVED = (409, "처분되지 않은 문서입니다")
    NOT_READY = (409, "추출이 끝나지 않은 문서입니다")
    PENDING_LOW_CONFIDENCE_ITEMS = (422, "신뢰도 낮음 항목을 먼저 확인해야 합니다")
    INVALID_DECISION = (422, "부적합 항목이 있는 로트는 승인할 수 없습니다")
    EXTRACTION_FAILED = (500, "AI 추출 처리에 실패했습니다")
    REPORT_GENERATION_FAILED = (500, "리포트 생성에 실패했습니다")
    INTERNAL_ERROR = (500, "서버 오류가 발생했습니다")  # 명세 외 추가 (예상 못 한 예외)

    @property
    def status_code(self) -> int:
        return self.value[0]

    @property
    def default_message(self) -> str:
        return self.value[1]


class AppException(Exception):
    def __init__(self, code: ErrorCode, message: str | None = None):
        self.code = code
        self.message = message or code.default_message
        super().__init__(self.message)


def _json(code: ErrorCode, message: str | None = None, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=code.status_code,
        content=error_body(code.name, message or code.default_message),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exc(_: Request, exc: AppException):
        headers = {"WWW-Authenticate": "Bearer"} if exc.code.status_code == 401 else None
        return _json(exc.code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # 필수 필드 누락, 타입 오류 등. FastAPI 기본은 422 지만 명세 422 코드들과 겹치지 않게 400 으로 보낸다.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = f"{loc}: {first.get('msg')}" if loc else ErrorCode.VALIDATION_ERROR.default_message
        return _json(ErrorCode.VALIDATION_ERROR, msg)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        mapping = {401: ErrorCode.UNAUTHORIZED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND}
        code = mapping.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return _json(code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error", exc_info=exc)
        return _json(ErrorCode.INTERNAL_ERROR)
