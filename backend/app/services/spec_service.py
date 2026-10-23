"""[담당: 장수민] 사내 규격 세트·항목 조회 (명세 2.5, v1.4안).

규격은 "세트" 단위로 고른다 (app/models/spec_set.py 참고).
  - 업로드 때 spec_set_code 를 주면 그 세트, 없으면 원자재의 기본 세트(is_default)를 문서에 연결한다.
  - 판정은 문서에 연결된 세트의 항목만 사용한다.

규격 조회·수정 API (명세 4.20, 4.21)
  - GET /specs        : 항목 목록. 원자재·세트로 거를 수 있다
  - GET /specs/sets   : 세트 목록 (v1.4안, 명세 외 추가)
  - PATCH /specs/{id} : 관리자 수정. 이후 업로드되는 문서부터 적용하고, 이미 판정한 문서는 바꾸지 않는다 (명세 4.21).
                        변경 사유(reason)는 필수이고, 바뀐 값을 spec_change_logs 에 남긴다 (v1.4).
                        규격 변경 시 재판정 옵션(v1.4안 rejudge)은 범위 결정(안건 5) 후 추가한다.
  - GET /specs/{id}/change-logs : 규격 변경 이력 (v1.4)
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppException, ErrorCode
from app.models import SpecChangeLog, SpecItem, SpecSet, User
from app.schemas.spec import SpecChangeLogOut, SpecItemOut, SpecSetOut, SpecUpdateRequest
from app.services.judgement.spec_rule import SpecRule


def material_exists(db: Session, material_code: str) -> bool:
    """등록된 규격 세트가 하나라도 있는 원자재인지."""
    return db.scalar(select(SpecSet.id).where(SpecSet.material_code == material_code).limit(1)) is not None


def get_default_set(db: Session, material_code: str) -> SpecSet | None:
    """원자재의 기본 세트. is_default 가 없으면 가장 먼저 등록된 세트."""
    return db.scalar(
        select(SpecSet)
        .where(SpecSet.material_code == material_code)
        .order_by(SpecSet.is_default.desc(), SpecSet.id)
        .limit(1)
    )


def resolve_spec_set(db: Session, material_code: str, spec_set_code: str | None = None) -> SpecSet:
    """업로드 시 문서에 연결할 규격 세트를 고른다.

    - 원자재에 세트가 없으면 400 UNKNOWN_MATERIAL
    - spec_set_code 가 없는 세트이거나 다른 원자재의 세트면 400 UNKNOWN_SPEC_SET (명세 외 추가)
    """
    if not material_exists(db, material_code):
        raise AppException(ErrorCode.UNKNOWN_MATERIAL)
    if not spec_set_code:
        return get_default_set(db, material_code)

    spec_set = db.scalar(select(SpecSet).where(SpecSet.code == spec_set_code))
    if spec_set is None or spec_set.material_code != material_code:
        raise AppException(ErrorCode.UNKNOWN_SPEC_SET, f"{material_code} 에 등록되지 않은 규격 세트입니다: {spec_set_code}")
    return spec_set


def get_specs(db: Session, spec_set_id: int) -> list[SpecItem]:
    return list(db.scalars(select(SpecItem).where(SpecItem.spec_set_id == spec_set_id).order_by(SpecItem.id)))


def get_rules(db: Session, spec_set_id: int) -> list[SpecRule]:
    """판정 모듈에 넘길 규격 목록 (세트 1개)."""
    return [SpecRule.from_model(s) for s in get_specs(db, spec_set_id)]


# ---------------------------------------------------------------------------
# 조회·수정 API
# ---------------------------------------------------------------------------
def list_items(db: Session, *, material_code: str | None = None, spec_set_code: str | None = None) -> list[SpecItemOut]:
    """GET /specs. 원자재 → 세트 → 항목 등록 순."""
    stmt = (select(SpecItem).join(SpecItem.spec_set)
            .options(joinedload(SpecItem.spec_set), joinedload(SpecItem.updater))
            .order_by(SpecSet.material_code, SpecSet.id, SpecItem.id))
    if material_code:
        stmt = stmt.where(SpecSet.material_code == material_code)
    if spec_set_code:
        stmt = stmt.where(SpecSet.code == spec_set_code)
    return [to_item_out(i) for i in db.scalars(stmt)]


def list_set_summaries(db: Session, material_code: str | None = None) -> list[SpecSetOut]:
    """GET /specs/sets. 원자재별로 기본 세트가 먼저 온다."""
    counts = {set_id: n for set_id, n in
              db.execute(select(SpecItem.spec_set_id, func.count()).group_by(SpecItem.spec_set_id))}
    stmt = select(SpecSet).order_by(SpecSet.material_code, SpecSet.is_default.desc(), SpecSet.id)
    if material_code:
        stmt = stmt.where(SpecSet.material_code == material_code)
    return [
        SpecSetOut(code=s.code, material_code=s.material_code, material_name=s.material_name, grade=s.grade,
                   version=s.version, source=s.source, description=s.description, is_default=s.is_default,
                   item_count=counts.get(s.id, 0))
        for s in db.scalars(stmt)
    ]


# 변경 이력에 남기는 필드와 순서 (요청에 보낸 순서와 관계없이 이 순서로 적는다)
_LOGGED_FIELDS = ("lsl", "usl", "unit")


def update_item(db: Session, spec_id: int, req: SpecUpdateRequest, user: User) -> SpecItemOut:
    """PATCH /specs/{id}. 보낸 필드만 바꾸고 수정자·수정 일시와 변경 이력을 남긴다.

    검사 순서: 규격 없음 404 → 사유 누락 400 REASON_REQUIRED → 범위 오류 400 INVALID_SPEC_RANGE
    실제로 바뀐 값이 없으면 이력은 남기지 않는다 (수정자·수정 일시는 갱신).
    """
    item = db.get(SpecItem, spec_id, with_for_update=True)
    if item is None:
        raise AppException(ErrorCode.SPEC_NOT_FOUND)
    reason = (req.reason or "").strip() or None
    if reason is None:
        raise AppException(ErrorCode.REASON_REQUIRED, "규격 변경 사유를 입력해야 합니다")
    changes = req.model_dump(exclude_unset=True, exclude={"reason"})
    if "unit" in changes:
        changes["unit"] = (changes["unit"] or "").strip() or None
    lsl = changes.get("lsl", item.lsl)
    usl = changes.get("usl", item.usl)
    if lsl is not None and usl is not None and lsl > usl:
        raise AppException(ErrorCode.INVALID_SPEC_RANGE)

    changed = [f for f in _LOGGED_FIELDS if f in changes and changes[f] != getattr(item, f)]
    if changed:
        db.add(SpecChangeLog(
            spec_item_id=item.id,
            before_value=", ".join(f"{f}: {_fmt_spec_value(getattr(item, f))}" for f in changed),
            after_value=", ".join(f"{f}: {_fmt_spec_value(changes[f])}" for f in changed),
            reason=reason,
            user_id=user.id,
        ))
    for field, value in changes.items():
        setattr(item, field, value)
    item.updated_by = user.id
    item.updated_at = func.now()
    db.commit()
    db.refresh(item)
    return to_item_out(item)


def list_change_logs(db: Session, spec_id: int) -> list[SpecChangeLogOut]:
    """GET /specs/{id}/change-logs. 오래된 순."""
    if db.get(SpecItem, spec_id) is None:
        raise AppException(ErrorCode.SPEC_NOT_FOUND)
    rows = db.scalars(
        select(SpecChangeLog).options(joinedload(SpecChangeLog.user))
        .where(SpecChangeLog.spec_item_id == spec_id)
        .order_by(SpecChangeLog.created_at, SpecChangeLog.id)
    )
    return [SpecChangeLogOut(before_value=r.before_value, after_value=r.after_value, reason=r.reason,
                             user_name=r.user.name, created_at=r.created_at) for r in rows]


def _fmt_spec_value(v) -> str:
    """이력 문자열용. 50.0 → "50", None → "없음"."""
    if v is None:
        return "없음"
    return f"{v:g}" if isinstance(v, float) else str(v)


def to_item_out(item: SpecItem) -> SpecItemOut:
    s = item.spec_set
    return SpecItemOut(
        id=item.id, material_code=s.material_code, material_name=s.material_name, item_name=item.item_name,
        unit=item.unit, lsl=item.lsl, usl=item.usl, spec_type=item.spec_type, grade=s.grade, source=item.source,
        updated_by=item.updater.name if item.updater else None, updated_at=item.updated_at,
        spec_set_code=s.code, version=s.version, is_required=item.is_required,
    )
