"""[담당: 홍채령] 대시보드 요약, 로트 추이 (4.18, 4.19)"""
from datetime import datetime

from pydantic import BaseModel


class DeviationByItem(BaseModel):
    item_name: str
    fail_count: int
    undetermined_count: int


class SupplierEditStat(BaseModel):
    """공급사별 사람 수정률 (운영 정책 7장). 공급사의 CoA 양식이 바뀌면 이 값이 갑자기 오른다."""
    supplier: str                            # 공급사를 알 수 없으면 "(미상)"
    documents: int                           # 처분 완료 문서 수
    edited_documents: int                    # 그중 담당자가 항목 값·항목명을 고친 문서 수
    edit_rate: float                         # edited_documents / documents (%)
    success_rate: float                      # 100 - edit_rate: 사람이 고치지 않고 처분까지 간 비율 (양식별 성공률의 대용)


class ItemEditStat(BaseModel):
    """항목별 사람 수정률 (운영 정책 7장)."""
    item_name: str
    items: int                               # 처분 완료 문서에 나온 이 항목의 수
    edited_items: int                        # 그중 담당자가 값·항목명을 고친 수
    edit_rate: float


class DashboardSummary(BaseModel):
    """GET /dashboard/summary (명세 4.18). 비율은 퍼센트(소수 첫째 자리), 처분 완료 문서가 없으면 0."""
    total_processed: int
    accept_count: int
    conditional_accept_count: int
    reject_count: int
    on_hold_count: int
    pass_rate: float
    avg_processing_time_sec: float           # 업로드부터 처분까지 걸린 시간. avg_time_to_decision_sec 와 같은 값 (이전 이름, 화면 전환 뒤 제거 예정)
    avg_time_to_decision_sec: float = 0.0    # 운영 정책 7장: "처분까지 걸린 시간". 사람이 검수를 시작하기 전 대기가 섞여 있다
    avg_system_processing_sec: float | None = None  # 운영 정책 7장: 시스템이 실제로 작동한 시간(추출 시작~종료). 기록이 없으면 null
    recommendation_match_rate: float
    auto_approve_rate: float                 # v1.4안. 정상 문서 중 사람 수정·확인 없이 승인 권고된 비율
    reviewed_item_ratio: float               # v1.4안. 사람이 수정·확인한 항목 / 전체 항목 (누락·참고 포함)
    human_edit_rate: float = 0.0             # 운영 정책 7장: 담당자가 항목 값·항목명을 고친 문서 / 처분 완료 문서 (%). 확인만 한 것은 제외
    edit_rate_by_supplier: list[SupplierEditStat] = []
    edit_rate_by_item: list[ItemEditStat] = []
    reason_code_counts: dict[str, int]       # v1.4안. 처분 시점에 남아 있는 사유코드별 항목 수 (많은 순)
    deviation_by_item: list[DeviationByItem]


class LotTrendPoint(BaseModel):
    lot_no: str | None
    supplier: str | None
    value: float | None                      # 사내 규격 단위로 환산한 값. 숫자로 못 읽은 값(검출 안 됨, 규격 복사 등)은 null
    value_qualifier: str | None              # less_than·less_equal 이면 실측값이 아니라 상한값 (프론트가 다른 모양으로 표시)
    judgement: str
    approved_at: datetime


class LotTrends(BaseModel):
    """GET /dashboard/lot-trends (명세 4.19). points 는 처분 일시 순."""
    item_name: str
    unit: str | None                         # 가장 최근 처분 문서의 사내 규격 단위. 점이 없으면 null
    spec_lsl: float | None
    spec_usl: float | None
    points: list[LotTrendPoint]
