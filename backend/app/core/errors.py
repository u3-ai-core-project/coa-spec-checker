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
    UNKNOWN_SPEC_SET = (400, "등록되지 않은 규격 세트입니다")  # 명세 외 추가 (v1.4안 규격 세트, 업로드 spec_set_code)
    UNKNOWN_ITEM_NAME = (400, "사내 규격에 없는 항목명입니다")
    REASON_REQUIRED = (400, "사유를 입력해야 합니다")
    INVALID_SPEC_RANGE = (400, "규격 하한이 상한보다 큽니다")
    INVALID_PASSWORD = (400, "비밀번호는 8자 이상이며 영문자와 숫자를 하나 이상 포함해야 합니다")  # 운영 정책 2단계 계정 관리
    WRONG_PASSWORD = (400, "현재 비밀번호가 올바르지 않습니다")  # 운영 정책 2단계 (401 이면 프론트가 로그아웃시키므로 400)
    VALIDATION_ERROR = (400, "요청 형식이 올바르지 않습니다")  # 명세 외 추가 (아래 핸들러 참고)
    INVALID_CREDENTIALS = (401, "아이디 또는 비밀번호가 올바르지 않습니다")
    UNAUTHORIZED = (401, "인증이 필요합니다")
    FORBIDDEN = (403, "권한이 없습니다")
    ACCOUNT_DISABLED = (403, "비활성화된 계정입니다. 관리자에게 문의하세요")  # 운영 정책 2단계
    ACCOUNT_LOCKED = (429, "로그인 시도가 너무 많아 계정이 잠겼습니다. 잠시 후 다시 시도하세요")  # 운영 정책 3단계
    PASSWORD_CHANGE_REQUIRED = (403, "비밀번호를 먼저 변경해야 합니다")  # 운영 정책 2단계 (첫 로그인·초기화 후)
    NOT_FOUND = (404, "요청한 경로를 찾을 수 없습니다")  # 명세 외 추가 (없는 URL)
    DOCUMENT_NOT_FOUND = (404, "존재하지 않는 문서입니다")
    ITEM_NOT_FOUND = (404, "문서에 존재하지 않는 항목입니다")
    USER_NOT_FOUND = (404, "존재하지 않는 사용자입니다")  # 운영 정책 2단계
    SPEC_NOT_FOUND = (404, "존재하지 않는 규격 항목입니다")
    NOTHING_TO_REVERT = (409, "되돌릴 규격 변경 이력이 없습니다")  # 운영 정책 5장
    USERNAME_TAKEN = (409, "이미 사용 중인 아이디입니다")  # 운영 정책 2단계
    CANNOT_CHANGE_SELF = (409, "본인 계정은 비활성화하거나 권한을 낮출 수 없습니다")  # 운영 정책 2단계
    LAST_ADMIN = (409, "활성 관리자가 최소 1명은 있어야 합니다")  # 운영 정책 2단계
    RETENTION_NOT_EXPIRED = (409, "보관 기간이 지나야 보관용 폴더로 옮길 수 있습니다")  # 운영 정책 1장
    ALREADY_ARCHIVED = (409, "이미 보관용 폴더로 옮긴 문서입니다")  # 운영 정책 1장
    DUPLICATE_FILE = (409, "같은 파일이 이미 접수되어 있습니다. 확인 후 다시 접수할 수 있습니다")  # 운영 정책 1장
    BATCH_NOT_DELETABLE = (409, "처분 완료되었거나 추출 중인 문서가 있는 묶음은 삭제할 수 없습니다")  # 운영 정책 1장
    ALREADY_APPROVED = (409, "이미 처분된 문서입니다")
    NOT_APPROVED = (409, "처분되지 않은 문서입니다")
    NOT_READY = (409, "추출이 끝나지 않은 문서입니다")
    REISSUE_UNRESOLVED = (409, "같은 로트의 CoA 가 여러 개입니다. 기준 버전을 먼저 선택해야 합니다")  # 운영 정책 8.2
    NOT_BASE_VERSION = (409, "기준 버전으로 선택되지 않은 문서는 처분할 수 없습니다")  # 운영 정책 8.2
    NOT_FAILED = (409, "추출에 실패한 문서만 다시 처리할 수 있습니다")  # 명세 외 추가 (POST /documents/{id}/retry)
    PENDING_LOW_CONFIDENCE_ITEMS = (422, "신뢰도 낮음 항목을 먼저 확인해야 합니다")
    INVALID_DECISION = (422, "부적합 항목이 있는 로트는 승인할 수 없습니다")
    STORAGE_FULL = (507, "저장 공간이 부족해 새 업로드를 받을 수 없습니다. 관리자에게 문의하세요")  # 운영 정책 1장
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
    def __init__(self, code: ErrorCode, message: str | None = None, headers: dict[str, str] | None = None,
                 data: dict | None = None):
        self.code = code
        self.message = message or code.default_message
        self.headers = headers  # 응답 헤더 추가 (예: 429 의 Retry-After)
        self.data = data        # 에러 응답의 data 에 넣을 추가 정보 (예: DUPLICATE_FILE 의 기존 문서 목록). 보통 None
        super().__init__(self.message)


def _json(code: ErrorCode, message: str | None = None, headers: dict | None = None,
          data: dict | None = None) -> JSONResponse:
    body = error_body(code.name, message or code.default_message)
    if data is not None:
        body["data"] = data
    return JSONResponse(status_code=code.status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exc(_: Request, exc: AppException):
        headers = {"WWW-Authenticate": "Bearer"} if exc.code.status_code == 401 else {}
        headers.update(exc.headers or {})
        return _json(exc.code, exc.message, headers or None, exc.data)

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
