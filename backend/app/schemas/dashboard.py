"""[담당: 홍채령] 대시보드 요약, 로트 추이 (4.18, 4.19)"""
from pydantic import BaseModel


class DeviationByItem(BaseModel):
    item_name: str
    fail_count: int
    undetermined_count: int


class DashboardSummary(BaseModel):
    """GET /dashboard/summary (명세 4.18). 비율은 퍼센트(소수 첫째 자리), 처분 완료 문서가 없으면 0."""
    total_processed: int
    accept_count: int
    conditional_accept_count: int
    reject_count: int
    on_hold_count: int
    pass_rate: float
    avg_processing_time_sec: float
    recommendation_match_rate: float
    auto_approve_rate: float                 # v1.4안. 정상 문서 중 사람 수정·확인 없이 승인 권고된 비율
    reviewed_item_ratio: float               # v1.4안. 사람이 수정·확인한 항목 / 판정 대상 항목 (참고 제외, 누락 포함)
    reason_code_counts: dict[str, int]       # v1.4안. 처분 시점에 남아 있는 사유코드별 항목 수 (많은 순)
    deviation_by_item: list[DeviationByItem]
