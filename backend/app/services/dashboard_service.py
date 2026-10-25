"""[담당: 홍채령] 대시보드 집계 (읽기 전용)"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.enums import DocumentStatus, FinalDecision, Judgement, LotRecommendation, Role
from app.core.errors import AppException, ErrorCode
from app.models import Document, User
from app.schemas.dashboard import DashboardSummary, DeviationByItem
from app.services.judgement.item_judge import REASON_NO_SPEC, REASON_QUALITATIVE

# 참고 항목 (명세 2.3: 사내 규격에 없는 항목, 정성 항목 → 판정하지 않음). 판정 근거 문구로 구분한다.
_REFERENCE_REASONS = {REASON_NO_SPEC, REASON_QUALITATIVE}

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

    return DashboardSummary(
        total_processed=total,
        accept_count=decisions[FinalDecision.ACCEPT],
        conditional_accept_count=decisions[FinalDecision.CONDITIONAL_ACCEPT],
        reject_count=decisions[FinalDecision.REJECT],
        on_hold_count=on_hold_count,
        pass_rate=_percent(accepted, total),
        avg_processing_time_sec=round(sum(durations) / len(durations), 1) if durations else 0.0,
        recommendation_match_rate=_percent(matched, len(comparable)),
        auto_approve_rate=_auto_approve_rate(approved),
        reviewed_item_ratio=_reviewed_item_ratio(approved),
        reason_code_counts=_reason_code_counts(approved),
        deviation_by_item=_deviation_by_item(approved),
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
    """처분 완료 문서의 판정 대상 항목 중 담당자가 수정·확인한 항목 비율.

    분모는 참고 항목을 빼고 누락 항목은 넣는다 (2026-10-25 결정). 누락 항목은 담당자가 자체 시험값을
    입력해 처리할 수 있지만, 참고 항목은 판정하지 않아 사람이 확인할 일이 없기 때문이다.
    """
    items = [i for d in docs for i in _items(d) if not _is_reference(i)]
    return _percent(sum(1 for i in items if i.get("reviewed")), len(items))


def _is_reference(item: dict) -> bool:
    return not item.get("reason_code") and item.get("judgement_reason") in _REFERENCE_REASONS


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
