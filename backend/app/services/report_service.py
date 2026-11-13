"""[담당: 장수민] 엑셀 검수 리포트 생성 (openpyxl, 로트 1건 = 1시트) (명세 4.16, v1.4안).

요청 시점에 만들어 바로 돌려준다 (저장·생성 상태 관리 없음). 실패하면 500 REPORT_GENERATION_FAILED.

시트 구성
  [로트 시트] 로트 1건당 1장. 시트 이름은 로트번호 (없으면 파일명)
    1. 문서 정보       협력사, 원자재, 로트, 시험일, 원산지, 협력사 적용 규격, 사내 규격 세트·등급·버전
    2. 로트 요약       판정별 항목 수, 로트 권고, 문서 정합성 오류, 후속 조치 안내
    3. 항목별 판정표   원문 표기, 정규화 값, 사내 규격, 판정(5종), 판정 근거, 이탈 폭, 신뢰도
                       + v1.4안: 사유코드, 해결 조건, 검수(확인·입력 출처)
                       처리가 필요한 항목이 위로 오도록 부적합 → 판정 불가 → 확인 필요 → 누락 → 적합 순 (명세 4.8)
    4. 수정 및 확인 이력 (수정자, 수정 사유 포함)
    5. 처분·보류 이력
    6. 최종 처분       처분, 처분자, 처분 일시, 사유. 미처분 문서는 비워서 출력
  [문의 초안 시트] v1.4안. 로트별 후속 조치 목록과 공급사 문의 메일 초안 (inquiry_draft.py, 템플릿 기반)

build_workbook() 은 문서 여러 건을 받을 수 있다. 리포트 화면의 여러 건 다운로드(UI 4-3)를 만들 때 그대로 쓰면 된다.
"""
import io
import logging
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.safe_log import log_exception
from app.core.enums import (
    ApprovalAction, DocumentStatus, FinalDecision, FollowUp, Judgement, LotRecommendation, NOT_READY_STATUSES,
    ReviewAction, ValueQualifier as Q, ValueSource,
)
from app.core.errors import AppException, ErrorCode
from app.models import ApprovalLog, Document, ReviewLog
from app.models.review_log import DOCUMENT_LOG_ITEM_ID
from app.schemas.extraction import ExtractionItem, ExtractionResult
from app.services import extraction_service, spec_service
from app.services.inquiry_draft import REASON_LABELS, build_follow_ups, build_inquiry_draft
from app.services.judgement.lot_recommend import FOLLOW_UP_GUIDE
from app.services.pseudonym import Pseudonymizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 화면과 같은 한글 표기 (UI 명세)
# ---------------------------------------------------------------------------
JUDGEMENT_KO = {Judgement.PASS: "적합", Judgement.FAIL: "부적합", Judgement.UNDETERMINED: "판정 불가",
                Judgement.MISSING: "누락", Judgement.CHECK: "확인 필요"}
RECOMMENDATION_KO = {LotRecommendation.APPROVE: "승인 권고", LotRecommendation.HOLD: "보류 권고",
                     LotRecommendation.REJECT: "불합격 권고"}
DECISION_KO = {FinalDecision.ACCEPT: "승인", FinalDecision.CONDITIONAL_ACCEPT: "조건부 승인",
               FinalDecision.REJECT: "불합격"}
STATUS_KO = {DocumentStatus.QUEUED: "대기", DocumentStatus.PROCESSING: "처리 중", DocumentStatus.EXTRACTED: "검수 전",
             DocumentStatus.IN_REVIEW: "검수 중", DocumentStatus.ON_HOLD: "보류", DocumentStatus.APPROVED: "처분 완료",
             DocumentStatus.FAILED: "오류"}
REVIEW_ACTION_KO = {ReviewAction.EDIT: "값 수정", ReviewAction.CONFIRM: "값 확인", ReviewAction.RENAME: "항목명 수정",
                    ReviewAction.RESPEC: "규격 세트 변경"}
VALUE_SOURCE_KO = {ValueSource.CORRECTION: "원문 수정", ValueSource.SUPPLIER_REPLY: "공급사 회신",
                   ValueSource.INTERNAL_TEST: "자체 시험"}
APPROVAL_ACTION_KO = {ApprovalAction.APPROVE: "처분", ApprovalAction.HOLD: "보류", ApprovalAction.CANCEL: "처분 취소"}
FOLLOW_UP_KO = {FollowUp.REQUEST_ACTUAL_VALUE: "실측값 요청", FollowUp.REQUEST_DETECTION_LIMIT: "검출한계 요청",
                FollowUp.INTERNAL_TEST: "자체 시험", FollowUp.REQUEST_SINGLE_VALUE: "개별값 요청",
                FollowUp.REQUEST_REISSUE: "CoA 재발행 요청", FollowUp.REQUEST_CORRECT_COA: "올바른 CoA 요청",
                FollowUp.OTHER: "기타"}

# 처리가 필요한 항목을 위로 (명세 4.8)
JUDGEMENT_ORDER = {Judgement.FAIL: 0, Judgement.UNDETERMINED: 1, Judgement.CHECK: 2, Judgement.MISSING: 3,
                   Judgement.PASS: 4}

# ---------------------------------------------------------------------------
# 스타일
# ---------------------------------------------------------------------------
FONT = "맑은 고딕"
TITLE = Font(name=FONT, size=14, bold=True)
SECTION = Font(name=FONT, size=11, bold=True, color="FFFFFF")
SECTION_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER = Font(name=FONT, bold=True)
HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
BODY = Font(name=FONT)
LABEL_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
JUDGEMENT_FILL = {
    Judgement.FAIL: PatternFill("solid", fgColor="F8CBAD"),
    Judgement.UNDETERMINED: PatternFill("solid", fgColor="FFE699"),
    Judgement.CHECK: PatternFill("solid", fgColor="FFF2CC"),
    Judgement.MISSING: PatternFill("solid", fgColor="E2EFDA"),
}

ITEM_COLUMNS = [  # (제목, 너비)
    ("No", 5), ("항목", 14), ("원문 항목명", 22), ("원문 값", 16), ("단위", 8), ("협력사 규격", 14),
    ("정규화 값", 16), ("사내 규격", 14), ("판정", 10), ("판정 근거", 34), ("이탈 폭", 9),
    ("사유코드", 22), ("해결 조건", 34), ("추출 신뢰도", 10), ("검수", 14),
]

# 이력 표는 판정표와 열 너비를 같이 쓰므로, 좁은 열(No 등)에 끼지 않게 여러 열을 합쳐 쓴다 (합계 15열)
LOG_SPANS = [2, 1, 1, 2, 2, 1, 4, 2]    # 일시, 항목, 작업, 이전 값, 이후 값, 입력 출처, 사유, 담당자
APPROVAL_SPANS = [2, 1, 1, 3, 6, 2]     # 일시, 작업, 처분, 후속 조치, 사유, 담당자


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def generate_report(db: Session, document_id: str, *, pseudonymize: bool = False) -> tuple[bytes, str]:
    """문서 1건의 리포트 (엑셀 바이너리, 다운로드 파일명).

    pseudonymize=True: 팀 밖 공유용. 사용자 이름을 "담당자 A" 같은 가명으로 바꾼다 (운영 정책 3장, pseudonym.py)

    - 없는 문서 404, 추출 전·실패 문서 409 NOT_READY
    - 그 밖의 생성 오류는 500 REPORT_GENERATION_FAILED (화면의 "재생성" 버튼이 이 API 를 다시 호출)
    """
    doc = db.get(Document, document_id, options=[joinedload(Document.uploader), joinedload(Document.approver),
                                                 joinedload(Document.extraction), joinedload(Document.spec_set)])
    if doc is None:
        raise AppException(ErrorCode.DOCUMENT_NOT_FOUND)
    if doc.status in NOT_READY_STATUSES or doc.extraction is None:
        raise AppException(ErrorCode.NOT_READY)
    try:
        content = build_workbook(db, [doc], pseudonymize=pseudonymize)
    except Exception as e:
        log_exception(logger, "리포트 생성 실패: %s", document_id, exc=e)
        raise AppException(ErrorCode.REPORT_GENERATION_FAILED) from None
    return content, report_file_name(doc, pseudonymize=pseudonymize)


def report_file_name(doc: Document, *, pseudonymize: bool = False) -> str:
    """예: CoA검수리포트_A0481544_20261017.xlsx (가명 처리본은 끝에 _가명)"""
    key = _safe(doc.lot_no or doc.file_name.rsplit(".", 1)[0], 40)
    return f"CoA검수리포트_{key}_{_now().strftime('%Y%m%d')}{'_가명' if pseudonymize else ''}.xlsx"


def build_workbook(db: Session, docs: Sequence[Document], *, pseudonymize: bool = False) -> bytes:
    """pseudonymize=True 면 파일 전체에서 같은 사람은 같은 가명 (여러 문서를 한 파일로 받을 때도)."""
    people = Pseudonymizer(db, enabled=pseudonymize)
    wb = Workbook()
    wb.remove(wb.active)
    used_names: set[str] = set()
    drafts: list[tuple[Document, ExtractionResult]] = []
    for doc in docs:
        result = extraction_service.get_result(doc)
        ws = wb.create_sheet(_sheet_name(doc, used_names))
        _write_lot_sheet(db, ws, doc, result, people)
        drafts.append((doc, result))
    _write_inquiry_sheet(wb.create_sheet("문의 초안"), drafts)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 로트 시트
# ---------------------------------------------------------------------------
def _write_lot_sheet(db: Session, ws: Worksheet, doc: Document, result: ExtractionResult,
                     people: Pseudonymizer | None = None) -> None:
    people = people or Pseudonymizer(enabled=False)
    for n, (_, width) in enumerate(ITEM_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(n)].width = width
    _print_setup(ws)
    ws["A1"] = "CoA 검수 리포트"
    ws["A1"].font = TITLE
    ws["A2"] = f"생성 일시: {_fmt_dt(_now())}"
    ws["A2"].font = BODY
    row = 4

    spec_set = doc.spec_set or spec_service.get_default_set(db, doc.material_code)

    # 1. 문서 정보
    row = _section(ws, row, "1. 문서 정보")
    row = _pairs(ws, row, [
        ("파일명", doc.file_name), ("협력사", doc.supplier), ("원자재", _join(doc.material_name, doc.material_code)),
        ("로트번호", doc.lot_no), ("입고 로트번호", doc.received_lot_no), ("시험일", _fmt_date(doc.test_date)),
        ("원산지", doc.origin), ("협력사 적용 규격", doc.applied_standard),
        ("사내 규격", _join(spec_set.code if spec_set else None,
                          " ".join(v for v in (spec_set.grade, spec_set.version) if v) if spec_set else None)),
        ("업로드", f"{people.user(doc.uploader)} / {_fmt_dt(doc.uploaded_at)}"), ("문서 상태", STATUS_KO.get(doc.status)),
    ])

    # 2. 로트 요약
    row = _section(ws, row + 1, "2. 로트 요약")
    s = result.summary
    present = [j for j in (Judgement.UNDETERMINED, Judgement.MISSING, Judgement.CHECK) if getattr(s, j.value) > 0]
    row = _pairs(ws, row, [
        ("판정별 항목 수", f"적합 {s.pass_} · 부적합 {s.fail} · 판정 불가 {s.undetermined} · "
                       f"누락 {s.missing} · 확인 필요 {s.check}"),
        ("로트 권고", RECOMMENDATION_KO.get(result.lot_recommendation)),
        ("문서 정합성 오류", "\n".join(f"{i.code.value}: {i.message}" for i in result.document_issues) or "없음"),
        ("후속 조치 안내", "\n".join(f"{JUDGEMENT_KO[j]}: {FOLLOW_UP_GUIDE[j]}" for j in present)
         or ("부적합 항목 확인 후 처분" if s.fail else "담당자 확인 후 승인")),
    ])

    # 3. 항목별 판정표
    row = _section(ws, row + 1, "3. 항목별 판정")
    row = _header(ws, row, [c for c, _ in ITEM_COLUMNS])
    items = sorted(result.items, key=lambda i: JUDGEMENT_ORDER.get(i.judgement, 9))
    for n, item in enumerate(items, start=1):
        values = [
            n, item.normalized_name, item.raw_name, item.raw_value, item.unit, item.raw_spec,
            _normalized_text(item), _spec_text(item), JUDGEMENT_KO.get(item.judgement), item.judgement_reason,
            item.deviation,
            f"{item.reason_code.value}\n({REASON_LABELS.get(item.reason_code, '')})" if item.reason_code else None,
            item.resolution.condition if item.resolution else None,
            item.confidence, _review_text(item),
        ]
        _row(ws, row, values)
        fill = JUDGEMENT_FILL.get(item.judgement)
        if fill:
            ws.cell(row=row, column=9).fill = fill
        ws.cell(row=row, column=14).number_format = "0.00"
        row += 1

    # 4. 수정 및 확인 이력
    row = _section(ws, row + 1, "4. 수정 및 확인 이력")
    row = _header(ws, row, ["일시", "항목", "작업", "이전 값", "이후 값", "입력 출처", "사유", "담당자"], LOG_SPANS)
    names = {i.item_id: i.normalized_name for i in result.items}
    logs = db.scalars(select(ReviewLog).options(joinedload(ReviewLog.reviewer))
                      .where(ReviewLog.document_id == doc.id).order_by(ReviewLog.reviewed_at, ReviewLog.id)).all()
    for log in logs:
        item_label = "(문서 전체)" if log.item_id == DOCUMENT_LOG_ITEM_ID else names.get(log.item_id, log.item_id)
        _row(ws, row, [_fmt_dt(log.reviewed_at), item_label,
                       REVIEW_ACTION_KO.get(log.action), log.before_value, log.after_value,
                       VALUE_SOURCE_KO.get(log.value_source) if log.value_source else None, people.text(log.reason),
                       people.user(log.reviewer)],
             LOG_SPANS)
        row += 1
    if not logs:
        row = _empty(ws, row)

    # 5. 처분·보류 이력
    row = _section(ws, row + 1, "5. 처분·보류 이력")
    row = _header(ws, row, ["일시", "작업", "처분", "후속 조치", "사유", "담당자"], APPROVAL_SPANS)
    alogs = db.scalars(select(ApprovalLog).options(joinedload(ApprovalLog.user))
                       .where(ApprovalLog.document_id == doc.id).order_by(ApprovalLog.created_at, ApprovalLog.id)).all()
    for log in alogs:
        _row(ws, row, [_fmt_dt(log.created_at), APPROVAL_ACTION_KO.get(log.action),
                       DECISION_KO.get(log.decision) if log.decision else None,
                       FOLLOW_UP_KO.get(log.follow_up) if log.follow_up else None, people.text(log.reason),
                       people.user(log.user)],
             APPROVAL_SPANS)
        row += 1
    if not alogs:
        row = _empty(ws, row)

    # 6. 최종 처분 (미처분이면 빈칸)
    row = _section(ws, row + 1, "6. 최종 처분")
    row = _pairs(ws, row, [
        ("AI 권고", RECOMMENDATION_KO.get(result.lot_recommendation)),
        ("최종 처분", DECISION_KO.get(doc.final_decision) if doc.final_decision else None),
        ("처분자", people.user(doc.approver)),
        ("처분 일시", _fmt_dt(doc.approved_at) if doc.approved_at else None),
        ("처분 사유", people.text(doc.decision_reason)),
    ])

    # 7. 판정 근거 버전 (운영 정책 6장). 이 기능 전에 만든 결과는 "기록 없음"
    row = _section(ws, row + 1, "7. 판정 근거 버전")
    _pairs(ws, row, version_rows(doc.extraction.versions if doc.extraction else None))


def version_rows(versions: dict | None) -> list[tuple[str, str | None]]:
    """리포트에 넣을 '판정 근거 버전' 행 (항목명, 값)."""
    if not versions:
        return [("기록", "기록 없음 (버전 기록 기능 전에 처리된 문서)")]
    e, j = versions.get("extraction") or {}, versions.get("judgement") or {}
    ai = e.get("ai_package") or {}
    llm = e.get("llm") or {}
    mapping = e.get("mapping_dictionary") or {}
    spec = j.get("spec_set") or {}
    return [
        ("추출 일시", _fmt_iso(e.get("read_at"))),
        ("추출기", _join(e.get("extractor"), f"{ai.get('name')} {ai.get('version')}" if ai else None)),
        ("LLM", f"{llm.get('host')} (모델: {llm.get('model') or '미기록'})" if llm.get("configured") else "사용 안 함"),
        ("매핑 사전", f"{mapping.get('count', 0)}건, 지문 {mapping.get('hash')}" if mapping else None),
        ("판정 일시", _fmt_iso(j.get("judged_at"))),
        ("판정 규격", _join(spec.get("code"), spec.get("version")) if spec else None),
        ("규격·정책 지문", f"규격 {spec.get('rules_hash')} / 정책 {j.get('policy_hash')}" if j else None),
        ("프로그램 버전", f"백엔드 {j.get('backend_version') or e.get('backend_version')}"),
    ]


def _fmt_iso(text: str | None) -> str | None:
    return _fmt_dt(datetime.fromisoformat(text)) if text else None


# ---------------------------------------------------------------------------
# 문의 초안 시트 (v1.4안)
# ---------------------------------------------------------------------------
def _write_inquiry_sheet(ws: Worksheet, drafts: list[tuple[Document, ExtractionResult]]) -> None:
    widths = [16, 12, 22, 26, 34, 30, 12]
    for n, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(n)].width = w
    _print_setup(ws)
    ws["A1"] = "후속 조치와 공급사 문의 초안"
    ws["A1"].font = TITLE
    ws["A2"] = "템플릿 기반 초안입니다. 숫자·근거는 판정 결과 값만 사용했습니다. 발송 전 담당자가 검토해 주세요."
    ws["A2"].font = BODY
    row = 4
    for doc, result in drafts:
        row = _section(ws, row, f"Lot {doc.lot_no or doc.file_name} — {doc.supplier or '공급사 미기재'}", span=7)
        follow = build_follow_ups(result)
        row = _header(ws, row, ["로트", "대상", "사유코드", "왜 문제인가", "해결 조건", "CoA 원문 값", "요청 대상"])
        for ln in follow.all:
            _row(ws, row, [doc.lot_no, ln.target, ln.code, ln.why or ln.label, ln.condition, ln.raw_value,
                           "공급사" if ln.to_supplier else "내부 확인"])
            row += 1
        if not follow.all:
            row = _empty(ws, row, "후속 조치 없음 (모든 항목 자동 검증 완료)")

        draft = build_inquiry_draft(result, supplier=doc.supplier, material_name=doc.material_name, lot_no=doc.lot_no)
        if draft:
            subject, body = draft
            row = _pairs(ws, row + 1, [("메일 제목", subject), ("메일 본문", body)], value_span=6, label_span=1)
        row += 1


# ---------------------------------------------------------------------------
# 셀 쓰기 도우미
# ---------------------------------------------------------------------------
def _print_setup(ws: Worksheet) -> None:
    """인쇄·PDF 변환 시 A4 가로, 너비를 한 쪽에 맞춤 (판정표가 여러 쪽으로 잘리지 않게)."""
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _section(ws: Worksheet, row: int, title: str, span: int = len(ITEM_COLUMNS)) -> int:
    ws.cell(row=row, column=1, value=title).font = SECTION
    for c in range(1, span + 1):
        ws.cell(row=row, column=c).fill = SECTION_FILL
    return row + 1


def _columns(count: int, spans: list[int] | None) -> list[tuple[int, int]]:
    """값 n 개를 놓을 (시작 열, 끝 열). spans 가 없으면 한 칸씩."""
    spans = spans or [1] * count
    out, col = [], 1
    for span in spans:
        out.append((col, col + span - 1))
        col += span
    return out


def _header(ws: Worksheet, row: int, titles: list[str], spans: list[int] | None = None) -> int:
    for t, (first, last) in zip(titles, _columns(len(titles), spans)):
        if last > first:
            ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
        cell = ws.cell(row=row, column=first)
        _set(cell, t)
        cell.font, cell.fill, cell.border = HEADER, HEADER_FILL, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return row + 1


def _row(ws: Worksheet, row: int, values: list, spans: list[int] | None = None) -> None:
    for v, (first, last) in zip(values, _columns(len(values), spans)):
        if last > first:
            ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
        cell = ws.cell(row=row, column=first)
        _set(cell, v)
        cell.font, cell.border, cell.alignment = BODY, BOX, WRAP


def _set(cell, value) -> None:
    """셀에 값을 넣는다. "=" 로 시작하는 문자열은 수식이 아니라 글자로 저장한다.

    CoA 원문에는 "=<20 ppm" 같은 표기가 흔하다. 그대로 넣으면 엑셀이 수식으로 해석해 오류(Err:510)가 나고,
    악의적인 문서라면 수식이 실행될 수도 있다 (CSV/수식 주입). 그래서 항상 문자열 형식으로 고정한다.
    """
    cell.value = value
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"


def _pairs(ws: Worksheet, row: int, pairs: list[tuple[str, object]], value_span: int = 6,
           label_span: int = 2) -> int:
    """'항목명 | 값' 표. 항목명 칸은 label_span 개, 값 칸은 value_span 개 열을 합친다.

    로트 시트의 A 열은 판정표의 좁은 No 열이라, 항목명은 A:B 두 칸을 합쳐 쓴다.
    """
    for label, value in pairs:
        if label_span > 1:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=label_span)
        lc = ws.cell(row=row, column=1)
        _set(lc, label)
        lc.font, lc.fill, lc.border, lc.alignment = HEADER, LABEL_FILL, BOX, WRAP
        first = label_span + 1
        ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=first + value_span - 1)
        vc = ws.cell(row=row, column=first)
        _set(vc, value)
        vc.font, vc.border, vc.alignment = BODY, BOX, WRAP
        lines = str(value).count("\n") + 1 if value else 1
        if lines > 1:
            ws.row_dimensions[row].height = min(15 * lines, 400)
        row += 1
    return row


def _empty(ws: Worksheet, row: int, text: str = "기록 없음") -> int:
    ws.cell(row=row, column=1, value=text).font = Font(name=FONT, italic=True, color="808080")
    return row + 1


# ---------------------------------------------------------------------------
# 값 표기
# ---------------------------------------------------------------------------
def _normalized_text(item: ExtractionItem) -> str | None:
    """정규화 값: 사내 규격 단위로 환산한 값 (부등호·검출 안 됨 표기 유지)."""
    q, v = item.value_qualifier, item.converted_value
    if q is None:
        return None
    if q == Q.NOT_DETECTED:
        return f"검출 안 됨 (검출한계 {item.detection_limit:g})" if item.detection_limit is not None else "검출 안 됨"
    if q == Q.TEXT or isinstance(v, str):
        return str(v)
    prefix = {Q.LESS_THAN: "< ", Q.LESS_EQUAL: "≤ "}.get(q, "")
    return f"{prefix}{v:g}" if v is not None else None


def _spec_text(item: ExtractionItem) -> str | None:
    lsl, usl = item.spec_lsl, item.spec_usl
    if lsl is not None and usl is not None:
        return f"{lsl:g} ~ {usl:g}"
    if usl is not None:
        return f"≤ {usl:g}"
    if lsl is not None:
        return f"≥ {lsl:g}"
    return None


def _review_text(item: ExtractionItem) -> str | None:
    if item.value_source is not None:
        return VALUE_SOURCE_KO.get(item.value_source)
    return "확인함" if item.reviewed else None


def _join(*parts: str | None) -> str | None:
    shown = [p for p in parts if p]
    return " / ".join(shown) if shown else None


def _now() -> datetime:
    return datetime.now(ZoneInfo(settings.DB_TIMEZONE))


def _fmt_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo(settings.DB_TIMEZONE)).strftime("%Y-%m-%d %H:%M")


def _fmt_date(d) -> str | None:
    return d.isoformat() if d else None


def _safe(text: str, limit: int) -> str:
    """시트 이름·파일명에 쓸 수 없는 문자 제거."""
    for ch in '[]:*?/\\"<>|':
        text = text.replace(ch, "_")
    return text.strip()[:limit] or "lot"


def _sheet_name(doc: Document, used: set[str]) -> str:
    """엑셀 시트 이름은 31자 이하·중복 불가. 같은 로트가 여러 건이면 (2), (3) 을 붙인다."""
    base = _safe(doc.lot_no or doc.file_name.rsplit(".", 1)[0], 27)
    name, n = base, 2
    while name.lower() in used:
        name = f"{base}({n})"
        n += 1
    used.add(name.lower())
    return name
