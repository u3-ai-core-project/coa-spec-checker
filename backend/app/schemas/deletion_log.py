"""[담당: 홍채령] 삭제 기록 응답 (운영 정책 1장, GET /deletion-logs)."""
from datetime import datetime

from app.core.enums import DeletionRule
from app.schemas.common import ORMModel


class DeletionLogItem(ORMModel):
    id: int
    document_id: str | None
    file_name: str
    file_size: int | None
    file_sha256: str | None
    material_code: str | None
    supplier: str | None
    lot_no: str | None
    received_lot_no: str | None
    batch_id: str | None
    status_at_delete: str | None
    uploaded_by: int | None
    uploaded_at: datetime | None
    deleted_by: int | None   # 자동 정리면 null
    deleted_at: datetime
    reason: str
    rule: DeletionRule
    approval_summary: list[dict]  # [{action, decision, follow_up, user_id, at, reason}]
    review_summary: dict          # {counts, reviewer_ids, first_reviewed_at, last_reviewed_at, edited_items, ...}
