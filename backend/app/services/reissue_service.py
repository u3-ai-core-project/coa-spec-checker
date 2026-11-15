"""[담당: 장수민] 재발행 버전 충돌 — 같은 원자재·같은 로트의 CoA 가 또 들어왔는지 확인한다 (운영 정책 8.2).

같은 로트인지는 로트번호의 대소문자·공백·구분 기호 차이를 무시하고 본다 (document_checks.normalize_lot).
상태는 저장하지 않고 문서들로부터 매번 계산한다. 문서가 삭제되면 묶음도 저절로 줄어든다.

  none          같은 로트의 다른 CoA 없음
  conflict      2건 이상이고 기준 버전을 아직 안 골랐음 → 확정 처분 불가
  review_needed conflict 인데 묶음 안에 이미 처분된 문서가 있음 → 처분은 자동으로 바꾸지 않고 재검토 대상으로 알린다.
                기준 버전을 고르기 전에는 처분 전 문서도 처분할 수 없다
  resolved      기준 버전을 골랐고, 그 뒤에 같은 로트 CoA 가 새로 들어오지 않았음 → 기준 버전 문서만 처분할 수 있다
보류·검수는 기준 버전을 고르기 전에도 할 수 있다. 막는 것은 확정 처분(approve)뿐이다.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DocumentStatus
from app.core.errors import AppException, ErrorCode
from app.models import Document, ReissueDecision, User
from app.schemas.reissue import ReissueAttentionGroup, ReissueInfo, ReissueVersion
from app.services.judgement.document_checks import normalize_lot


@dataclass
class ReissueState:
    status: str
    material_code: str
    lot_key: str
    group: list[Document] = field(default_factory=list)
    decision: ReissueDecision | None = None


def _group(db: Session, material_code: str, lot_key: str) -> list[Document]:
    candidates = db.scalars(
        select(Document).where(Document.material_code == material_code, Document.lot_no.is_not(None))
        .order_by(Document.uploaded_at, Document.id)
    )
    return [d for d in candidates if normalize_lot(d.lot_no) == lot_key]


def _state_of(db: Session, material_code: str, lot_key: str, group: list[Document]) -> ReissueState:
    if not lot_key or len(group) < 2:
        return ReissueState("none", material_code, lot_key, group)
    ids = [d.id for d in group]
    decision = db.scalar(
        select(ReissueDecision)
        .where(ReissueDecision.material_code == material_code, ReissueDecision.lot_key == lot_key,
               ReissueDecision.base_document_id.in_(ids))
        .order_by(ReissueDecision.created_at.desc(), ReissueDecision.id.desc()).limit(1)
    )
    if decision is not None and decision.created_at >= max(d.uploaded_at for d in group):
        return ReissueState("resolved", material_code, lot_key, group, decision)
    approved_exists = any(d.status == DocumentStatus.APPROVED for d in group)
    return ReissueState("review_needed" if approved_exists else "conflict", material_code, lot_key, group, decision)


def get_state(db: Session, doc: Document) -> ReissueState:
    key = normalize_lot(doc.lot_no)
    if not key:
        return ReissueState("none", doc.material_code, key, [doc])
    return _state_of(db, doc.material_code, key, _group(db, doc.material_code, key))


def status_of(db: Session, doc: Document) -> str:
    return get_state(db, doc).status


def to_info(db: Session, doc: Document) -> ReissueInfo:
    state = get_state(db, doc)
    base_id = state.decision.base_document_id if state.status == "resolved" else None
    return ReissueInfo(
        status=state.status,
        material_code=state.material_code,
        lot_no=doc.lot_no,
        base_document_id=base_id,
        decided_reason=state.decision.reason if state.status == "resolved" else None,
        versions=[
            ReissueVersion(
                document_id=d.id, file_name=d.file_name, supplier=d.supplier, lot_no=d.lot_no, status=d.status,
                lot_recommendation=d.lot_recommendation, final_decision=d.final_decision,
                uploaded_at=d.uploaded_at, approved_at=d.approved_at, is_base=d.id == base_id,
            )
            for d in state.group
        ] if state.status != "none" else [],
    )


def choose_base(db: Session, doc: Document, base_document_id: str, reason: str | None, user: User) -> ReissueInfo:
    """기준 버전을 고른다. 사유 필수, 같은 로트 묶음(2건 이상) 안의 문서여야 한다. commit 까지 한다."""
    state = get_state(db, doc)
    if state.status == "none":
        raise AppException(ErrorCode.VALIDATION_ERROR, "같은 로트의 다른 CoA 가 없어 기준 버전을 고를 수 없습니다")
    reason = (reason or "").strip()
    if not reason:
        raise AppException(ErrorCode.REASON_REQUIRED, "기준 버전을 고른 사유를 입력해야 합니다")
    if base_document_id not in {d.id for d in state.group}:
        raise AppException(ErrorCode.VALIDATION_ERROR, "같은 로트 묶음에 없는 문서는 기준 버전으로 고를 수 없습니다")
    db.add(ReissueDecision(material_code=state.material_code, lot_key=state.lot_key,
                           base_document_id=base_document_id, reason=reason, user_id=user.id))
    db.commit()
    db.refresh(doc)
    return to_info(db, doc)


def ensure_can_approve(db: Session, doc: Document) -> None:
    """확정 처분 전 검사. 기준 버전을 안 골랐으면 409 REISSUE_UNRESOLVED, 기준이 아닌 문서면 409 NOT_BASE_VERSION."""
    state = get_state(db, doc)
    if state.status in ("conflict", "review_needed"):
        raise AppException(ErrorCode.REISSUE_UNRESOLVED)
    if state.status == "resolved" and state.decision.base_document_id != doc.id:
        raise AppException(ErrorCode.NOT_BASE_VERSION)


def list_attention(db: Session) -> list[ReissueAttentionGroup]:
    """기준 버전을 골라야 하거나(conflict) 재검토가 필요한(review_needed) 로트 묶음."""
    docs = db.scalars(select(Document).where(Document.lot_no.is_not(None)).order_by(Document.uploaded_at, Document.id))
    groups: dict[tuple[str, str], list[Document]] = {}
    for d in docs:
        key = normalize_lot(d.lot_no)
        if key:
            groups.setdefault((d.material_code, key), []).append(d)
    out: list[ReissueAttentionGroup] = []
    for (material, key), group in groups.items():
        if len(group) < 2:
            continue
        state = _state_of(db, material, key, group)
        if state.status in ("conflict", "review_needed"):
            out.append(ReissueAttentionGroup(material_code=material, lot_no=group[-1].lot_no, status=state.status,
                                             document_ids=[d.id for d in group]))
    return out
