"""[담당: 홍채령] 로그에 개인정보·문서 내용을 남기지 않기 (운영 정책 3장, 6장).

"로그와 오류 메시지에 이름, 비밀번호, 인증 정보, 문서 내용을 남기지 않는다."
- 사람은 이름·아이디 대신 사용자 id(숫자)로 남긴다
- 로그인 실패처럼 id 를 모를 때(없는 아이디)는 아이디 대신 username_tag() 의 짧은 표식을 남긴다

예외 메시지(str(e))에는 문서 값, 항목명, LLM 답, 사용자 입력이 섞일 수 있다.
그래서 기본으로는 예외 종류와 발생 위치(파일:줄)만 남기고 메시지는 남기지 않는다.
원인을 자세히 봐야 하는 개발 환경에서만 LOG_DEBUG_DETAIL=true 로 켜서 전체 traceback 을 남긴다.

    try: ...
    except Exception as e:
        log_exception(logger, "문서 추출 실패: %s", document_id, exc=e)
"""
import hashlib
import hmac
import logging
import traceback

from app.core.config import settings


def exception_summary(exc: BaseException) -> str:
    """'ValueError at app/x.py:12 <- app/y.py:34' 처럼 예외 종류와 위치만. 메시지는 넣지 않는다."""
    frames = traceback.extract_tb(exc.__traceback__)[-3:]
    where = " <- ".join(f"{_short(f.filename)}:{f.lineno}" for f in reversed(frames))
    name = type(exc).__name__
    cause = exc.__cause__ or exc.__context__
    text = f"{name} at {where}" if where else name
    if cause is not None and cause is not exc:
        text += f" (원인: {type(cause).__name__})"
    return text


def _short(path: str) -> str:
    for marker in ("/app/", "/coa_ai/", "/site-packages/"):
        if marker in path:
            return marker.strip("/") + "/" + path.split(marker, 1)[1]
    return path.rsplit("/", 1)[-1]


def log_exception(logger: logging.Logger, msg: str, *args, exc: BaseException, level: int = logging.ERROR) -> None:
    """예외 기록. 기본: 메시지 + 예외 종류·위치. LOG_DEBUG_DETAIL=true: 전체 traceback (개발 환경 전용)."""
    if settings.LOG_DEBUG_DETAIL:
        logger.log(level, msg, *args, exc_info=exc)
    else:
        logger.log(level, msg + " [%s]", *args, exception_summary(exc))


def username_tag(username: str) -> str:
    """아이디 대신 로그에 남길 짧은 표식 (예: 'u-3f9a1c0b'). 같은 아이디는 늘 같은 표식이라 반복 시도를 묶어 볼 수 있다.

    아이디 칸에 비밀번호를 잘못 넣는 일이 흔해서 아이디 원문은 남기지 않는다.
    JWT_SECRET 을 섞어(HMAC) 만들므로, 비밀키 없이 흔한 아이디를 하나씩 넣어 보는 방법으로는 원래 아이디를 알아낼 수 없다.
    """
    key = username.strip().lower().encode()
    return "u-" + hmac.new(settings.JWT_SECRET.encode(), key, hashlib.sha256).hexdigest()[:8]
