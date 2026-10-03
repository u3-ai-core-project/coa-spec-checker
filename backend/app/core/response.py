"""[담당: 장수민] 공통 응답 형식 {success, data, error} (명세 1장).

라우터에서는 반환값을 ok() 로 감싼다.

    @router.get("/{id}", response_model=ApiResponse[DocumentDetail])
    def get_document(...):
        return ok(service.get(...))
"""
from typing import Any


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def error_body(code: str, message: str) -> dict:
    return {"success": False, "data": None, "error": {"code": code, "message": message}}
