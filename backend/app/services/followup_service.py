"""[담당: 장수민] 후속 조치·공급사 문의 초안 (명세 v1.4안 4.22, 기획안 v2 7.2·UC09).

멘토님 피드백 ②의 "담당자가 어떤 작업을 해야 하는지"를 문서 1건 기준으로 돌려준다.
  1. 후속 조치 목록: 공급사에 요청할 것 / 내부에서 확인할 것 (inquiry_draft.build_follow_ups)
  2. 보류 후속 조치 추천: 보류 화면에서 follow_up 기본값으로 쓴다
  3. 문의 초안: 이 로트 1통
  4. 같은 공급사 묶음: 처리 중(extracted·in_review·on_hold)인 같은 공급사 문서의 요청을 메일 1통으로

초안 생성기 (Drafter)
  설정 INQUIRY_DRAFTER 로 고른다. 기본은 템플릿. AI 파트(고도영 님) 모듈을 연결하면 AI 초안을 쓰고,
  AI 가 실패하면 템플릿으로 대신한다 (source=template_fallback). 생성기를 준비하다 실패한 경우
  (ai 패키지 미설치, 알 수 없는 설정값)도 같다. 숫자·근거는 판정 결과 값만 넘긴다.
읽기만 하고 DB 에 쓰지 않는다.
"""
import logging
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.enums import DocumentStatus, NOT_READY_STATUSES
from app.core.errors import AppException, ErrorCode
from app.models import Document
from app.schemas.followup import FollowUpLineOut, FollowUpsResponse, InquiryDraftOut, OpenDocumentOut
from app.services import extraction_service
from app.services.inquiry_draft import LotRequest, TemplateDrafter, build_follow_ups, suggest_follow_up

logger = logging.getLogger(__name__)

OPEN_STATUSES = (DocumentStatus.EXTRACTED, DocumentStatus.IN_REVIEW, DocumentStatus.ON_HOLD)


class Drafter(Protocol):
    """문의 초안 생성기 형식. supplier 와 로트별 요청 목록을 받아 (제목, 본문) 을 돌려준다."""
    source: str

    def draft(self, supplier: str | None, lots: list[LotRequest]) -> tuple[str, str]: ...


def get_drafter(mode: str | None = None) -> Drafter:
    """mode: "template" / "ai". 없으면 설정 INQUIRY_DRAFTER (기본 template)."""
    mode = mode or settings.INQUIRY_DRAFTER
    if mode == "template":
        return TemplateDrafter()
    if mode == "ai":
        from app.pipeline.ai_drafter import AIDrafter  # ai/ 패키지가 필요해서 지연 import
        return AIDrafter()
    raise ValueError(f"알 수 없는 INQUIRY_DRAFTER 설정: {mode}")


def get_follow_ups(db: Session, document_id: str, draft_mode: str | None = None) -> FollowUpsResponse:
    """draft_mode: "ai" 면 AI 초안, "template" 이면 템플릿, 없으면 설정값 (10.25 결정 7: 기본은 템플릿, 요청할 때만 AI)."""
    doc = db.get(Document, document_id, options=[joinedload(Document.extraction)])
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    result = extraction_service.get_result(doc)
    if doc.status in NOT_READY_STATUSES or result is None:
        raise AppException(ErrorCode.NOT_READY)

    follow = build_follow_ups(result)
    this_lot = LotRequest(doc.lot_no, doc.material_name, follow.supplier_lines)

    # 같은 공급사의 처리 중 문서 (공급사명이 있을 때만, 대소문자·앞뒤 공백 무시)
    open_docs: list[OpenDocumentOut] = []
    lots: list[LotRequest] = []
    if doc.supplier:
        others = db.scalars(
            select(Document).options(joinedload(Document.extraction))
            .where(func.lower(func.trim(Document.supplier)) == doc.supplier.strip().lower(),
                   Document.status.in_(OPEN_STATUSES))
            .order_by(Document.uploaded_at, Document.id)
        ).unique()
        for other in others:
            other_result = extraction_service.get_result(other)
            if other_result is None:
                continue
            lines = this_lot.lines if other.id == doc.id else build_follow_ups(other_result).supplier_lines
            if lines:
                open_docs.append(OpenDocumentOut(document_id=other.id, lot_no=other.lot_no, status=other.status,
                                                 request_count=len(lines)))
                lots.append(this_lot if other.id == doc.id else LotRequest(other.lot_no, other.material_name, lines))

    return FollowUpsResponse(
        document_id=doc.id,
        supplier=doc.supplier,
        lot_no=doc.lot_no,
        suggested_follow_up=suggest_follow_up(follow),
        supplier_lines=[_line_out(ln) for ln in follow.supplier_lines],
        internal_lines=[_line_out(ln) for ln in follow.internal_lines],
        draft=_draft(doc.supplier, [this_lot], draft_mode) if this_lot.lines else None,
        open_documents=open_docs,
        combined_draft=_draft(doc.supplier, lots, draft_mode) if len(lots) >= 2 else None,
    )


def _draft(supplier: str | None, lots: list[LotRequest], mode: str | None = None) -> InquiryDraftOut:
    """설정된 생성기로 초안을 만들고, 실패하면 템플릿으로 대신한다.

    생성기 준비(get_drafter)도 try 안에서 한다. INQUIRY_DRAFTER=ai 인데 ai 패키지가 없거나 설정값이 잘못되면
    500 대신 템플릿 초안을 쓴다. 템플릿 생성기 자체가 실패하면 대신할 것이 없으므로 그대로 올린다.
    """
    drafter: Drafter | None = None
    try:
        drafter = get_drafter(mode) if mode else get_drafter()
        subject, body = drafter.draft(supplier, lots)
        source = drafter.source
    except Exception:
        used = mode or settings.INQUIRY_DRAFTER
        if isinstance(drafter, TemplateDrafter) or (drafter is None and used == "template"):
            raise
        stage = "준비" if drafter is None else "생성"
        logger.exception("문의 초안 생성기 %s 실패 (mode=%s), 템플릿으로 대체", stage, used)
        subject, body = TemplateDrafter().draft(supplier, lots)
        source = "template_fallback"
    return InquiryDraftOut(subject=subject, body=body, source=source, lot_nos=[lot.lot_no for lot in lots])


def _line_out(ln) -> FollowUpLineOut:
    return FollowUpLineOut(target=ln.target, code=ln.code, label=ln.label, why=ln.why, condition=ln.condition,
                           raw_value=ln.raw_value, to_supplier=ln.to_supplier)
