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
    """PATCH /specs/{id} (명세 4.21). 보낸 필드만 바꾼다. 범위를 지우려면 null 을 보낸다.

    reason(변경 사유, v1.4)은 필수다. 비었거나 공백뿐이면 400 REASON_REQUIRED (검사는 spec_service 에서 한다.
    필드 누락을 VALIDATION_ERROR 로 보내면 다른 API 의 REASON_REQUIRED 와 코드가 달라지기 때문).
    """
    lsl: float | None = Field(None, description="하한. null 이면 하한 없음")
    usl: float | None = Field(None, description="상한. null 이면 상한 없음")
    unit: str | None = Field(None, description="단위")
    reason: str | None = Field(None, description="변경 사유 (v1.4, 필수)")
    rejudge: bool = Field(False, description="true 이면 이 규격 세트로 판정한 처분 전 문서(추출됨·검수 중·보류)를 새 규격으로 다시 판정")


class RejudgedDocument(BaseModel):
    """규격 변경 때 다시 판정한 문서 1건. 판정이 바뀐 항목과 로트 권고 변화를 알려 준다."""
    document_id: str
    lot_recommendation_before: str | None
    lot_recommendation_after: str | None
    changed_items: list[str] = Field(description="판정이 바뀐 항목명")


class SpecPreviewOut(BaseModel):
    """POST /specs/{id}/preview 응답 (운영 정책 5장). 저장하지 않고, 적용했을 때 다시 판정될 문서에 생길 변화만 계산한다."""
    changed_fields: list[str] = Field(description="실제로 바뀌는 필드 (lsl, usl, unit). 비어 있으면 바뀌는 값이 없음")
    target_documents: int = Field(description="이 규격 세트로 판정한 처분 전 문서 수 (rejudge=true 로 적용하면 다시 판정되는 문서)")
    affected_documents: int = Field(description="그중 항목 판정이나 로트 권고가 바뀌는 문서 수")
    recommendation_changed_documents: int = Field(description="그중 로트 권고가 바뀌는 문서 수")
    documents: list[RejudgedDocument] = Field(description="영향받는 문서 목록")


class SpecRevertRequest(BaseModel):
    """POST /specs/{id}/revert. 가장 최근 변경을 되돌린다. 사유는 필수 (검사는 spec_service 에서 한다)."""
    reason: str | None = Field(None, description="되돌리는 사유 (필수)")
    rejudge: bool = Field(False, description="true 이면 처분 전 문서도 되돌린 규격으로 다시 판정")


class SpecUpdateOut(SpecItemOut):
    """PATCH /specs/{id} 응답. rejudge=true 로 요청했을 때만 rejudged_documents 가 채워진다."""
    rejudged_documents: list[RejudgedDocument] = []


class SpecChangeLogOut(BaseModel):
    """GET /specs/{id}/change-logs 1건 (명세 v1.4 4.21-1). 바뀐 필드만 문자열로 담는다. 예) "usl: 50" → "usl: 30"."""
    before_value: str
    after_value: str
    reason: str
    user_name: str
    created_at: datetime
