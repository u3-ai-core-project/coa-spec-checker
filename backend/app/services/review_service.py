"""[담당: 장수민] 검수: 추출 결과 조회, 항목 수정·확인, 재판정, review_logs 기록 (명세 4.8~4.11, v1.4안).

공통 흐름 (수정·확인)
  1. 문서를 잠그고(SELECT ... FOR UPDATE) 상태 확인
       queued·processing·failed → 409 NOT_READY,  approved → 409 ALREADY_APPROVED
  2. 항목 1개를 다시 판정 (판정·이탈 폭은 프론트가 보내지 않고 서버가 계산, 명세 4.9)
  3. 누락 항목 다시 맞추기 (항목명을 고치면 누락 대상이 바뀜) → 교차 규칙·집계·로트 권고 재계산
  4. review_logs 기록, 문서 상태 extracted·on_hold → in_review, JSON review_status 동기화, 저장

수정 사유 (v1.4)
  값을 입력하는 PATCH 는 reason 이 필수다. 검사 순서: 문서 없음 404 → 상태 409 → 항목 없음 404 → 사유 누락 400
  → 항목명 오류 400. 사유는 이번 요청으로 남는 이력(edit, rename)에 같이 저장한다.

자동 재판정 (v1.4안)
  회신값(실측값, 검출한계, 자체 시험값)을 PATCH 로 넣으면 2단계에서 그 값으로 판정한다.
  해결 조건(resolution)을 만족하면 그대로 적합이 되고 reason_code·resolution 이 사라진다.

규격 세트를 바꿔 다시 판정 (POST /documents/{id}/rejudge, 멘토님 피드백: 검수 화면 규격 드롭다운)
  AI 추출은 다시 하지 않고 저장된 추출 결과를 다른 규격 세트로 판정한다.
  apply=false : 미리보기. 문서·이력을 바꾸지 않는다. 처분 완료 문서도 볼 수 있다 (다른 기준으로 시험해 보는 용도)
  apply=true  : 문서의 규격 세트를 바꾸고 저장한다. 처분 전 문서만, 사유 필수, review_logs 에 respec 이력.
  검사 순서: 문서 없음 404 → 상태 409 → 규격 세트 400 UNKNOWN_SPEC_SET → 사유 누락 400 (apply=true)

잠금을 거는 이유: 두 사람이 같은 문서의 다른 항목을 동시에 고치면 JSON 전체를 덮어써 한쪽 수정이 사라질 수 있다.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import (
    DocumentIssueCode, DocumentStatus, MappingSource, NOT_READY_STATUSES, ReviewAction, ValueQualifier as Q,
    ValueSource, status_to_review_status,
)
from app.core.errors import AppException, ErrorCode
from app.models import Document, ReviewLog, SpecSet, User
from app.models.review_log import DOCUMENT_LOG_ITEM_ID
from app.schemas.extraction import DocumentIssue, ExtractionItem, ExtractionResult
from app.schemas.review import (
    ItemUpdateRequest, RejudgeItemChange, RejudgeRequest, RejudgeResponse, ReviewedItem, ReviewLogOut, SpecSetRef,
)
from app.services import extraction_service, mapping_service, spec_service
from app.services.judgement.document_checks import check_spec_version
from app.services.judgement.engine import refresh_summary
from app.services.judgement.item_judge import current_override, evaluate_item, rejudge_item
from app.services.judgement.missing_items import build_missing_items
from app.services.judgement.policy import default_policy
from app.services.judgement.resolutions import fmt_value
from app.services.judgement.spec_rule import SpecRule, name_key


# ---------------------------------------------------------------------------
# 조회 (4.8, 4.11)
# ---------------------------------------------------------------------------
def get_extraction(db: Session, document_id: str) -> ExtractionResult:
    """추출·판정 결과 JSON (명세 4.8). 추출 전·실패 문서는 409 NOT_READY."""
    doc = _get_document(db, document_id)
    result = extraction_service.get_result(doc)
    if doc.status in NOT_READY_STATUSES or result is None:
        raise AppException(ErrorCode.NOT_READY)
    return result


def list_review_logs(db: Session, document_id: str) -> list[ReviewLogOut]:
    """수정·확인 이력, 오래된 순 (명세 4.11)."""
    _get_document(db, document_id)
    rows = db.scalars(
        select(ReviewLog).options(joinedload(ReviewLog.reviewer))
        .where(ReviewLog.document_id == document_id)
        .order_by(ReviewLog.reviewed_at, ReviewLog.id)
    )
    return [to_log_out(r) for r in rows]


# ---------------------------------------------------------------------------
# 항목 수정 (4.9) — 값 수정, 회신값 입력, 항목명 수정
# ---------------------------------------------------------------------------
def update_item(
    db: Session, document_id: str, item_id: str, req: ItemUpdateRequest, user: User
) -> tuple[ExtractionItem, ExtractionResult, list[ReviewLog]]:
    doc = _lock_reviewable(db, document_id)
    result = extraction_service.get_result(doc)
    specs = _specs_of(db, doc)
    by_name = {name_key(s.item_name): s for s in specs}
    policy = default_policy()
    idx, item = _find_item(result, item_id)
    reason = req.clean_reason
    if req.has_value and reason is None:
        raise AppException(ErrorCode.REASON_REQUIRED, "값을 수정할 때는 수정 사유를 입력해야 합니다")
    logs: list[ReviewLog] = []

    # ---- 1) 항목명 수정 ----
    if req.new_name is not None and name_key(req.new_name) != name_key(item.normalized_name):
        spec = by_name.get(name_key(req.new_name))
        if spec is None:
            raise AppException(ErrorCode.UNKNOWN_ITEM_NAME, f"사내 규격에 없는 항목명입니다: {req.new_name}")
        if item.mapping_source == MappingSource.SPEC:
            raise AppException(ErrorCode.VALIDATION_ERROR, "누락 항목은 항목명을 바꿀 수 없습니다")
        if any(i.item_id != item.item_id and name_key(i.normalized_name) == name_key(spec.item_name)
               and not _is_untouched_missing(i) for i in result.items):
            raise AppException(ErrorCode.VALIDATION_ERROR, f"이미 '{spec.item_name}' 항목이 있습니다")

        logs.append(_log(doc, item, ReviewAction.RENAME, item.normalized_name, spec.item_name, user, reason=reason))
        if item.raw_name:
            mapping_service.upsert_manual(db, material_code=doc.material_code, raw_name=item.raw_name,
                                          normalized_name=spec.item_name, user_id=user.id)
        renamed = item.model_copy(update={"normalized_name": spec.item_name, "mapping_source": MappingSource.MANUAL})
        item = rejudge_item(renamed, spec, policy=policy)  # 새 규격으로 다시 판정 (검수 상태 유지)

    # ---- 2) 값 수정 / 회신값 입력 ----
    spec = by_name.get(name_key(item.normalized_name))
    if req.has_value:
        before = display_value(item, spec)
        item = evaluate_item(item, spec, override=req.to_parsed(), reviewed=True,
                             value_source=req.value_source or ValueSource.CORRECTION, policy=policy)
        logs.append(_log(doc, item, ReviewAction.EDIT, before, display_value(item, spec), user,
                         value_source=item.value_source, reason=reason))

    result.items[idx] = item
    _sync_missing_items(result, specs, policy)
    refresh_summary(result, specs, policy)
    _save(db, doc, result, logs)
    return _find_item(result, item_id)[1], result, logs


# ---------------------------------------------------------------------------
# 값 확인 (4.10)
# ---------------------------------------------------------------------------
def confirm_item(
    db: Session, document_id: str, item_id: str, user: User
) -> tuple[ExtractionItem, ExtractionResult, ReviewLog]:
    """원본을 보고 추출값이 맞다고 확인. 값은 바꾸지 않고 신뢰도 조건만 빼고 다시 판정한다.

    검출한계 미기재(ND_NO_LOD)·규격 복사처럼 값 자체가 부족한 경우는 확인해도 예외로 남는다 (명세 4.10).
    """
    doc = _lock_reviewable(db, document_id)
    result = extraction_service.get_result(doc)
    specs = _specs_of(db, doc)
    policy = default_policy()
    idx, item = _find_item(result, item_id)
    if _is_untouched_missing(item):
        raise AppException(ErrorCode.VALIDATION_ERROR, "누락 항목은 확인할 값이 없습니다. 값을 입력해 주세요")

    spec = next((s for s in specs if name_key(s.item_name) == name_key(item.normalized_name)), None)
    shown = display_value(item, spec)
    item = evaluate_item(item, spec, reviewed=True, override=current_override(item),
                         value_source=item.value_source, policy=policy)
    log = _log(doc, item, ReviewAction.CONFIRM, shown, shown, user)

    result.items[idx] = item
    refresh_summary(result, specs, policy)
    _save(db, doc, result, [log])
    return _find_item(result, item_id)[1], result, log


# ---------------------------------------------------------------------------
# 규격 세트를 바꿔 다시 판정 (POST /documents/{id}/rejudge)
# ---------------------------------------------------------------------------
def rejudge_by_spec_set(db: Session, document_id: str, req: RejudgeRequest, user: User) -> RejudgeResponse:
    """문서를 다른 규격 세트로 다시 판정한다. apply=false 는 미리보기, apply=true 는 저장 (commit 까지 한다)."""
    doc = _lock_reviewable(db, document_id) if req.apply else _get_ready_document(db, document_id)
    if not req.code:
        raise AppException(ErrorCode.VALIDATION_ERROR, "spec_set_code 를 입력해야 합니다")
    target = spec_service.resolve_spec_set(db, doc.material_code, req.code)
    reason = req.clean_reason
    if req.apply and reason is None:
        raise AppException(ErrorCode.REASON_REQUIRED, "규격 세트를 바꿀 때는 변경 사유를 입력해야 합니다")

    current = doc.spec_set or spec_service.get_default_set(db, doc.material_code)
    stored = extraction_service.get_result(doc)
    if current is not None and current.id == target.id:
        # 이미 이 세트로 판정한 문서. 저장된 결과를 그대로 보여 주고 아무것도 바꾸지 않는다
        return _rejudge_response(doc.id, applied=False, target=target, previous=current, before=stored, after=stored,
                                 changes=[])

    after, _ = rejudge_result(stored.model_copy(deep=True), spec_service.get_rules(db, target.id), target)
    changes = _item_changes(stored, after)
    if req.apply:
        doc.spec_set_id = target.id
        doc.spec_set = target
        log = _log(doc, _document_marker(), ReviewAction.RESPEC, current.code if current else None, target.code,
                   user, reason=reason)
        _save(db, doc, after, [log])
    return _rejudge_response(doc.id, applied=req.apply, target=target, previous=current, before=stored, after=after,
                             changes=changes)


def _get_ready_document(db: Session, document_id: str) -> Document:
    """미리보기용. 잠그지 않고, 처분 완료 문서도 허용한다. 추출 전·실패 문서는 409 NOT_READY."""
    doc = _get_document(db, document_id)
    if doc.status in NOT_READY_STATUSES or doc.extraction is None:
        raise AppException(ErrorCode.NOT_READY)
    return doc


def _document_marker() -> ExtractionItem:
    """문서 단위 이력(_log)에 넘길 가짜 항목. item_id 만 쓰인다."""
    return ExtractionItem.model_construct(item_id=DOCUMENT_LOG_ITEM_ID)


def _item_changes(before: ExtractionResult, after: ExtractionResult) -> list[RejudgeItemChange]:
    """규격 세트를 바꾸자 판정이 달라진 항목. 항목명으로 맞춘다 (누락 항목의 item_id 는 세트마다 새로 붙으므로)."""
    old = {name_key(i.normalized_name): i for i in before.items}
    new = {name_key(i.normalized_name): i for i in after.items}
    out: list[RejudgeItemChange] = []
    for key in [*old, *(k for k in new if k not in old)]:
        b, a = old.get(key), new.get(key)
        if (b.judgement if b else None) != (a.judgement if a else None):
            out.append(RejudgeItemChange(item_name=(a or b).normalized_name,
                                         before=b.judgement if b else None, after=a.judgement if a else None))
    return out


def _spec_ref(spec_set: SpecSet | None) -> SpecSetRef | None:
    return SpecSetRef(code=spec_set.code, grade=spec_set.grade, version=spec_set.version) if spec_set else None


def _rejudge_response(document_id: str, *, applied: bool, target: SpecSet, previous: SpecSet | None,
                      before: ExtractionResult, after: ExtractionResult,
                      changes: list[RejudgeItemChange]) -> RejudgeResponse:
    return RejudgeResponse(
        document_id=document_id, applied=applied, spec_set=_spec_ref(target), previous_spec_set=_spec_ref(previous),
        lot_recommendation_before=before.lot_recommendation, lot_recommendation_after=after.lot_recommendation,
        summary_before=before.summary, summary_after=after.summary, changed_items=changes, result=after,
    )


# ---------------------------------------------------------------------------
# 응답 변환
# ---------------------------------------------------------------------------
def to_reviewed_item(item: ExtractionItem) -> ReviewedItem:
    return ReviewedItem.model_validate(item.model_dump(include=set(ReviewedItem.model_fields)))


def to_log_out(log: ReviewLog) -> ReviewLogOut:
    return ReviewLogOut(
        item_id=log.item_id, action=log.action, before_value=log.before_value, after_value=log.after_value,
        value_source=log.value_source, reason=log.reason, reviewer_name=log.reviewer.name,
        reviewed_at=log.reviewed_at,
    )


def display_value(item: ExtractionItem, spec: SpecRule | None = None) -> str:
    """이력에 남길 값 문자열. 담당자가 값을 넣은 적이 없으면 CoA 원문, 넣었으면 그 값(사내 규격 단위)."""
    if item.value_source is None:
        return item.raw_value or ""
    unit = spec.unit if spec else None
    q, v, dl = item.value_qualifier, item.converted_value, item.detection_limit
    if q == Q.NOT_DETECTED:
        return f"검출 안 됨 (검출한계 {fmt_value(dl, unit)})" if dl is not None else "검출 안 됨"
    if q == Q.TEXT or isinstance(v, str):
        return str(v)
    prefix = {Q.LESS_THAN: "< ", Q.LESS_EQUAL: "≤ "}.get(q, "")
    return prefix + fmt_value(v, unit)


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------
def _get_document(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    return doc


def _lock_reviewable(db: Session, document_id: str) -> Document:
    """수정·확인 전에 문서 행을 잠그고 검수 가능한 상태인지 확인한다."""
    doc = db.get(Document, document_id, with_for_update=True, populate_existing=True)
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    if doc.status == DocumentStatus.APPROVED:
        raise AppException(ErrorCode.ALREADY_APPROVED)
    if doc.status in NOT_READY_STATUSES or doc.extraction is None:
        raise AppException(ErrorCode.NOT_READY)
    return doc


def _specs_of(db: Session, doc: Document) -> list[SpecRule]:
    spec_set = doc.spec_set or spec_service.get_default_set(db, doc.material_code)
    return spec_service.get_rules(db, spec_set.id) if spec_set else []


def rejudge_result(
    result: ExtractionResult, specs: list[SpecRule], spec_set: SpecSet | None = None
) -> tuple[ExtractionResult, list[str]]:
    """저장된 결과를 새 규격으로 다시 판정한다. DB 를 쓰지 않는 계산이며 result 를 직접 고쳐 돌려준다.

    돌려주는 값: (새 결과, 판정이 바뀐 항목명).
    서버가 만든 누락 항목은 버리고 새 규격으로 다시 만든다. 담당자가 확인·입력한 항목은 그 상태를 유지한다.
    spec_set 을 주면 규격 버전 불일치(SPEC_VERSION_MISMATCH)도 그 세트의 버전으로 다시 계산한다.
    다른 문서 정합성 오류(로트·날짜·제품)는 규격 세트와 무관하므로 그대로 둔다.
    """
    policy = default_policy()
    by_name = {name_key(s.item_name): s for s in specs}
    before = {i.item_id: i.judgement for i in result.items}
    names = {i.item_id: i.normalized_name for i in result.items}

    result.items = [rejudge_item(i, by_name.get(name_key(i.normalized_name)), policy=policy)
                    for i in result.items if not _is_untouched_missing(i)]
    _sync_missing_items(result, specs, policy)
    if spec_set is not None:
        result.document_issues = _with_spec_version_issue(result, spec_set.version)
    refresh_summary(result, specs, policy)

    changed = [names[i.item_id] for i in result.items if i.item_id in before and before[i.item_id] != i.judgement]
    return result, changed


def rejudge_document(doc: Document, specs: list[SpecRule], spec_set: SpecSet | None = None) -> tuple[ExtractionResult, list[str]]:
    """규격이 바뀐 뒤 문서를 새 규격으로 다시 판정해 저장한다 (검수 상태 유지, 문서 상태는 그대로).

    commit 은 호출한 쪽에서 한다. 계산은 rejudge_result 가 한다.
    """
    result, changed = rejudge_result(extraction_service.get_result(doc), specs, spec_set)
    doc.lot_recommendation = result.lot_recommendation
    doc.extraction.result = result.to_json()
    doc.extraction.updated_at = datetime.now(timezone.utc)
    return result, changed


def _with_spec_version_issue(result: ExtractionResult, version: str | None) -> list[DocumentIssue]:
    """document_issues 에서 규격 버전 불일치만 새 세트 버전으로 다시 계산한다 (같은 자리에 두고, 없던 것이면 끝에 붙인다)."""
    fresh = check_spec_version(result.applied_standard, version)
    out: list[DocumentIssue] = []
    for issue in result.document_issues:
        if issue.code != DocumentIssueCode.SPEC_VERSION_MISMATCH:
            out.append(issue)
        elif fresh is not None:
            out.append(fresh)
            fresh = None
    if fresh is not None:
        out.append(fresh)
    return out


def _find_item(result: ExtractionResult, item_id: str) -> tuple[int, ExtractionItem]:
    for n, i in enumerate(result.items):
        if i.item_id == item_id:
            return n, i
    raise AppException(ErrorCode.ITEM_NOT_FOUND)


def _is_untouched_missing(item: ExtractionItem) -> bool:
    """서버가 만든 누락 항목 중 담당자가 아직 값을 넣지 않은 것 (교차 규칙으로 판정된 Pb 포함)."""
    return item.mapping_source == MappingSource.SPEC and item.value_source is None and not item.reviewed


def _sync_missing_items(result: ExtractionResult, specs: list[SpecRule], policy) -> None:
    """항목명 수정 후 누락 항목을 다시 맞춘다. result.items 를 직접 고친다.

    예) "Sodium" 을 Na 로 고치면 기존 Na 누락 항목은 없어지고, 반대로 Na 였던 항목을 다른 이름으로 바꾸면 Na 누락이 생긴다.
    담당자가 값을 넣은 누락 항목은 유지한다. 기존 누락 항목은 item_id 를 그대로 쓰고, 새로 생기면 다음 번호를 붙인다.
    """
    kept = [i for i in result.items if not _is_untouched_missing(i)]
    old_missing = {name_key(i.normalized_name): i for i in result.items if _is_untouched_missing(i)}
    used = {i.item_id for i in result.items}
    by_name = {name_key(s.item_name): s for s in specs}

    next_no = 1
    added: list[ExtractionItem] = []
    for m in build_missing_items(kept, specs):
        key = name_key(m.normalized_name)
        if key in old_missing:
            added.append(old_missing[key])
            continue
        while f"spec-{next_no:03d}" in used:
            next_no += 1
        new_id = f"spec-{next_no:03d}"
        used.add(new_id)
        added.append(evaluate_item(m.model_copy(update={"item_id": new_id}), by_name[key], policy=policy))
    result.items = kept + added


def _log(doc: Document, item: ExtractionItem, action: ReviewAction, before: str | None, after: str | None,
         user: User, value_source: ValueSource | None = None, reason: str | None = None) -> ReviewLog:
    log = ReviewLog(document_id=doc.id, item_id=item.item_id, action=action, before_value=before,
                    after_value=after, value_source=value_source, reason=reason, reviewer_id=user.id)
    # reviewer 관계는 저장 후 id 로 다시 읽는다 (user 가 다른 세션 객체일 수 있어 직접 붙이지 않음)
    return log


def _save(db: Session, doc: Document, result: ExtractionResult, logs: list[ReviewLog]) -> None:
    # 검수가 시작되면 extracted·on_hold → in_review (명세 2.6, 4.9, 4.10)
    if doc.status in (DocumentStatus.EXTRACTED, DocumentStatus.ON_HOLD):
        doc.status = DocumentStatus.IN_REVIEW
    result.review_status = status_to_review_status(doc.status)
    doc.lot_recommendation = result.lot_recommendation
    doc.extraction.result = result.to_json()
    doc.extraction.updated_at = datetime.now(timezone.utc)
    db.add_all(logs)
    db.commit()
    for log in logs:
        db.refresh(log)  # reviewed_at (DB 기본값) 채우기
