"""[담당: 홍채령] 대시보드 집계 (읽기 전용)"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.enums import DocumentStatus, FinalDecision, Judgement, LotRecommendation, ReviewAction, Role
from app.core.errors import AppException, ErrorCode
from app.models import Document, ReviewLog, User
from app.models.review_log import DOCUMENT_LOG_ITEM_ID
from app.schemas.dashboard import (
    DashboardSummary, DeviationByItem, ItemEditStat, LotTrendPoint, LotTrends, SupplierEditStat,
)

# 로트 권고와 최종 처분이 "일치"하는 조합 (명세 4.18).
# 보류 권고는 대응하는 처분이 없어 권고 일치율 계산에서 뺀다 (2026-10-11 팀 결정).
_MATCHING_DECISION = {
    LotRecommendation.APPROVE: FinalDecision.ACCEPT,
    LotRecommendation.REJECT: FinalDecision.REJECT,
}


def resolve_uploader_filter(user: User, scope: str | None, user_id: int | None) -> int | None:
    """조회할 업로더 id. None 이면 전체. USER 가 scope=all 이나 user_id 를 쓰면 403."""
    if user.role != Role.ADMIN:
        if scope == "all" or user_id is not None:
            raise AppException(ErrorCode.FORBIDDEN)
        return user.id
    if user_id is not None:
        return user_id
    return user.id if scope == "mine" else None


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=ZoneInfo(settings.DB_TIMEZONE))


def _in_period(column, date_from: date | None, date_to: date | None) -> list:
    """from, to 는 한국 시간 기준 날짜이며 양 끝을 포함한다."""
    conditions = []
    if date_from:
        conditions.append(column >= _day_start(date_from))
    if date_to:
        conditions.append(column < _day_start(date_to + timedelta(days=1)))
    return conditions


def _percent(part: int, total: int) -> float:
    """소수 첫째 자리 퍼센트 (예: 20/24 → 83.3)."""
    return round(part / total * 100, 1) if total else 0.0


def get_summary(
    db: Session, uploaded_by: int | None, date_from: date | None, date_to: date | None,
    material_code: str | None = None,
) -> DashboardSummary:
    """처분 완료 문서는 처분 일시(approved_at), 보류 문서는 업로드 일시 기준으로 기간을 거른다."""
    owner = [Document.uploaded_by == uploaded_by] if uploaded_by is not None else []
    if material_code:
        owner.append(Document.material_code == material_code)

    approved = list(
        db.scalars(
            select(Document)
            .options(selectinload(Document.extraction))
            .where(Document.status == DocumentStatus.APPROVED, *owner, *_in_period(Document.approved_at, date_from, date_to))
        )
    )
    on_hold_count = db.scalar(
        select(func.count()).where(
            Document.status == DocumentStatus.ON_HOLD, *owner, *_in_period(Document.uploaded_at, date_from, date_to)
        )
    )

    decisions = Counter(d.final_decision for d in approved)
    total = len(approved)
    accepted = decisions[FinalDecision.ACCEPT] + decisions[FinalDecision.CONDITIONAL_ACCEPT]
    # 권고 일치율 분모: 승인 권고·불합격 권고 문서만. 보류 권고 문서는 분모에서 뺀다.
    comparable = [d for d in approved if d.lot_recommendation in _MATCHING_DECISION]
    matched = sum(1 for d in comparable if _MATCHING_DECISION[d.lot_recommendation] == d.final_decision)
    durations = [(d.approved_at - d.uploaded_at).total_seconds() for d in approved if d.approved_at]
    work = [(d.processing_finished_at - d.processing_started_at).total_seconds() for d in approved
            if d.processing_started_at and d.processing_finished_at]
    edited = _edited_items(db, approved)
    avg_decision = round(sum(durations) / len(durations), 1) if durations else 0.0

    return DashboardSummary(
        total_processed=total,
        accept_count=decisions[FinalDecision.ACCEPT],
        conditional_accept_count=decisions[FinalDecision.CONDITIONAL_ACCEPT],
        reject_count=decisions[FinalDecision.REJECT],
        on_hold_count=on_hold_count,
        pass_rate=_percent(accepted, total),
        avg_processing_time_sec=avg_decision,
        avg_time_to_decision_sec=avg_decision,
        avg_system_processing_sec=round(sum(work) / len(work), 1) if work else None,
        recommendation_match_rate=_percent(matched, len(comparable)),
        auto_approve_rate=_auto_approve_rate(approved),
        reviewed_item_ratio=_reviewed_item_ratio(approved),
        human_edit_rate=_percent(sum(1 for d in approved if edited.get(d.id)), total),
        edit_rate_by_supplier=_edit_rate_by_supplier(approved, edited),
        edit_rate_by_item=_edit_rate_by_item(approved, edited),
        reason_code_counts=_reason_code_counts(approved),
        deviation_by_item=_deviation_by_item(approved),
    )


def _edited_items(db: Session, docs: list[Document]) -> dict[str, set[str]]:
    """{문서 ID: 담당자가 값(edit)이나 항목명(rename)을 고친 항목 ID 집합}. 확인(confirm)과 규격 세트 변경(respec)은 수정이 아니다."""
    if not docs:
        return {}
    rows = db.execute(
        select(ReviewLog.document_id, ReviewLog.item_id)
        .where(ReviewLog.document_id.in_([d.id for d in docs]),
               ReviewLog.action.in_([ReviewAction.EDIT, ReviewAction.RENAME]),
               ReviewLog.item_id != DOCUMENT_LOG_ITEM_ID)
    )
    out: dict[str, set[str]] = {}
    for document_id, item_id in rows:
        out.setdefault(document_id, set()).add(item_id)
    return out


def _edit_rate_by_supplier(docs: list[Document], edited: dict[str, set[str]]) -> list[SupplierEditStat]:
    """공급사별 사람 수정률. 수정률 높은 순, 같으면 문서 많은 순.

    CoA 양식을 따로 저장하지 않으므로 공급사를 양식의 대용으로 쓴다 (공급사마다 양식이 다르다).
    """
    total: Counter[str] = Counter()
    touched: Counter[str] = Counter()
    for d in docs:
        name = (d.supplier or "").strip() or "(미상)"
        total[name] += 1
        touched[name] += 1 if edited.get(d.id) else 0
    stats = [SupplierEditStat(supplier=n, documents=total[n], edited_documents=touched[n],
                              edit_rate=_percent(touched[n], total[n]),
                              success_rate=round(100 - _percent(touched[n], total[n]), 1))
             for n in total]
    return sorted(stats, key=lambda s: (-s.edit_rate, -s.documents, s.supplier))


def _edit_rate_by_item(docs: list[Document], edited: dict[str, set[str]]) -> list[ItemEditStat]:
    """항목별 사람 수정률. 수정률 높은 순, 같으면 항목 많은 순. 누락 항목(서버가 만든 것)도 사람이 값을 넣으면 수정으로 센다."""
    total: Counter[str] = Counter()
    touched: Counter[str] = Counter()
    for d in docs:
        for item in _items(d):
            name = item.get("normalized_name")
            if not name:
                continue
            total[name] += 1
            if item.get("item_id") and item["item_id"] in edited.get(d.id, ()):
                touched[name] += 1
    stats = [ItemEditStat(item_name=n, items=total[n], edited_items=touched[n], edit_rate=_percent(touched[n], total[n]))
             for n in total]
    return sorted(stats, key=lambda s: (-s.edit_rate, -s.items, s.item_name))


def get_lot_trends(
    db: Session, item_name: str, uploaded_by: int | None, date_from: date | None, date_to: date | None,
    material_code: str | None = None,
) -> LotTrends:
    """한 항목의 로트별 값 추이 (명세 4.19, 확장). 처분 완료 문서만, 처분 일시(approved_at) 순.

    - 필터(scope, user_id, from, to, material_code)는 4.18 요약과 같다. 기간은 처분 일시 기준
    - 항목은 표준 항목명(normalized_name)이 item_name 과 같은 것. 그 항목이 없는 문서는 점을 만들지 않는다
    - value 는 사내 규격 단위로 환산한 값(converted_value)이 숫자일 때만 넣고, 아니면 null
    - unit, spec_lsl, spec_usl 은 가장 최근 처분 문서의 그 항목 값. 문서마다 규격 세트가 다를 수 있어서
      화면의 기준선은 가장 최근 규격으로 그린다
    """
    conditions = [Document.status == DocumentStatus.APPROVED, Document.approved_at.is_not(None),
                  *_in_period(Document.approved_at, date_from, date_to)]
    if uploaded_by is not None:
        conditions.append(Document.uploaded_by == uploaded_by)
    if material_code:
        conditions.append(Document.material_code == material_code)
    docs = db.scalars(
        select(Document).options(selectinload(Document.extraction)).where(*conditions)
        .order_by(Document.approved_at, Document.id)
    )

    points: list[LotTrendPoint] = []
    latest: dict | None = None
    for doc in docs:
        item = next((i for i in _items(doc) if i.get("normalized_name") == item_name), None)
        if item is None:
            continue
        value = item.get("converted_value")
        points.append(LotTrendPoint(
            lot_no=doc.lot_no,
            supplier=doc.supplier,
            value=float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
            value_qualifier=item.get("value_qualifier"),
            judgement=item.get("judgement"),
            approved_at=doc.approved_at,
        ))
        latest = item
    return LotTrends(
        item_name=item_name,
        unit=(latest.get("spec_unit") or latest.get("unit")) if latest else None,
        spec_lsl=latest.get("spec_lsl") if latest else None,
        spec_usl=latest.get("spec_usl") if latest else None,
        points=points,
    )


def _items(doc: Document) -> list[dict]:
    return doc.extraction.result.get("items", []) if doc.extraction else []


def _auto_approve_rate(docs: list[Document]) -> float:
    """정상 문서 중 사람이 항목을 수정·확인하지 않았는데 승인 권고된 비율 (명세 v1.4안 4.18).

    운영 데이터에는 정답이 없으므로 '정상 문서' 는 담당자가 최종 승인(accept)한 문서로 본다.
    조건부 승인은 조건이 붙은 문서라 정상에서 뺀다. 분모를 정상 문서로 둔 것은 평가 스크립트의
    '정상 자동 처리율' 과 같은 정의다 (2026-10-18 결정).
    """
    normal = [d for d in docs if d.final_decision == FinalDecision.ACCEPT]
    auto = [d for d in normal
            if d.lot_recommendation == LotRecommendation.APPROVE and not any(i.get("reviewed") for i in _items(d))]
    return _percent(len(auto), len(normal))


def _reviewed_item_ratio(docs: list[Document]) -> float:
    """처분 완료 문서의 전체 항목(누락·참고 항목 포함) 중 담당자가 수정·확인한 항목 비율.

    명세 v1.4안 문구('사람이 수정·확인한 항목 / 전체 항목')와 검수 화면의 '전체 항목' 개수에 맞춰
    참고 항목도 분모에 넣는다 (2026-10-25 결정).
    """
    items = [i for d in docs for i in _items(d)]
    return _percent(sum(1 for i in items if i.get("reviewed")), len(items))


def _reason_code_counts(docs: list[Document]) -> dict[str, int]:
    """처분 완료 문서에 남아 있는 사유코드별 항목 수.

    회신값으로 해결된 항목은 재판정 때 사유코드가 지워지므로 여기에 잡히지 않는다.
    '처음 판정 때의 사유코드' 를 세려면 판정 결과에 그 값을 따로 남겨야 한다 (장수민 님과 논의 필요).
    """
    counts = Counter(i["reason_code"] for d in docs for i in _items(d) if i.get("reason_code"))
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _deviation_by_item(docs: list[Document]) -> list[DeviationByItem]:
    """항목별 부적합·판정 불가 수. 둘 다 0인 항목은 빼고, 부적합 많은 순으로 정렬."""
    fails: Counter[str] = Counter()
    undetermined: Counter[str] = Counter()
    for doc in docs:
        for item in _items(doc):
            name = item.get("normalized_name")
            if item.get("judgement") == Judgement.FAIL:
                fails[name] += 1
            elif item.get("judgement") == Judgement.UNDETERMINED:
                undetermined[name] += 1
    names = sorted(set(fails) | set(undetermined), key=lambda n: (-fails[n], -undetermined[n], n))
    return [DeviationByItem(item_name=n, fail_count=fails[n], undetermined_count=undetermined[n]) for n in names]
