"""[담당: 장수민] 공통 응답 스키마. Swagger 문서에 응답 형식이 보이도록 response_model 로 사용."""
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None


class Page(BaseModel, Generic[T]):
    """GET /documents 의 data 형식 (명세 4.5)."""
    total: int
    items: list[T]


class ORMModel(BaseModel):
    """ORM 객체에서 바로 변환할 응답 스키마의 베이스."""
    model_config = ConfigDict(from_attributes=True)
