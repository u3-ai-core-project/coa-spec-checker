"""[담당: 장수민] 규격 조회·수정 (명세 4.20, 4.21, v1.4안 규격 세트)."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import SpecType


class SpecItemOut(BaseModel):
    """GET /specs 항목 1개 (명세 4.20 + v1.4안 세트 정보).

    material_code, material_name, grade 는 v1.4안부터 규격 세트에 있지만, 명세 4.20 응답 형식을 유지하려고
    항목마다 같이 내려준다.
    """
    id: int
    material_code: str
    material_name: str
    item_name: str
    unit: str | None
    lsl: float | None
    usl: float | None
    spec_type: SpecType
    grade: str | None
    source: str | None
    updated_by: str | None
    updated_at: datetime | None
    # ---- v1.4안 ----
    spec_set_code: str
    version: str | None
    is_required: bool


class SpecSetOut(BaseModel):
    """GET /specs/sets (v1.4안, 명세 외 추가). 업로드 화면의 원자재·규격 세트 선택, 규격 관리 화면 필터에 사용."""
    code: str
    material_code: str
    material_name: str
    grade: str | None
    version: str | None
    source: str | None
    description: str | None
    is_default: bool
    item_count: int


class SpecUpdateRequest(BaseModel):
    """PATCH /specs/{id} (명세 4.21). 보낸 필드만 바꾼다. 범위를 지우려면 null 을 보낸다."""
    lsl: float | None = Field(None, description="하한. null 이면 하한 없음")
    usl: float | None = Field(None, description="상한. null 이면 상한 없음")
    unit: str | None = Field(None, description="단위")
