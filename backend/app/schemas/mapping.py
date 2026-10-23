"""[담당: 장수민] 매핑 사전·환산표 조회, 매핑 삭제 응답 (명세 v1.4 4.23, 화면 5-2)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ItemMappingSource


class MappingOut(BaseModel):
    """GET /mappings 1건."""
    id: int
    material_code: str
    raw_name: str = Field(description="협력사 항목명 (CoA 표기)")
    normalized_name: str = Field(description="사내 표준 항목명")
    source: ItemMappingSource = Field(description="seed(초기값) | manual(담당자 항목명 수정으로 누적)")
    created_by: str | None = Field(description="등록한 사용자 이름. 초기값이면 null")
    created_at: datetime


class MappingDeleted(BaseModel):
    """DELETE /mappings/{id}."""
    id: int


class UnitConversionOut(BaseModel):
    """단위 환산 1건. from 단위 값 × factor = to 단위 값."""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: str = Field(alias="from")
    to: str
    factor: float


class OxideConversionOut(BaseModel):
    """산화물 → 원소 환산 1건. 산화물 기준 값 × factor = 원소 기준 값."""
    oxide: str
    element: str | None
    factor: float


class ConversionsOut(BaseModel):
    """GET /mappings/conversions. 서버 설정값이라 조회만 된다."""
    units: list[UnitConversionOut]
    oxides: list[OxideConversionOut]
