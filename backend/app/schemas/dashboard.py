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
    deviation_by_item: list[DeviationByItem]
