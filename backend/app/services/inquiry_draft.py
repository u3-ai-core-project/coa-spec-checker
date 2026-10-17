"""[담당: 장수민] 후속 조치 목록과 공급사 문의 초안 — 템플릿 기반 (명세 v1.4안 4.16, 4.22 준비).

멘토님 피드백 ②의 "담당자가 어떤 작업을 해야 하는지"를 문서 단위로 모은다.
  - 예외 항목(reason_code 있는 항목)과 문서 정합성 오류를 "공급사에 요청할 것"과 "내부에서 할 것"으로 나눈다.
  - 공급사 요청은 메일 1통 분량의 초안으로 만든다. 숫자와 근거는 서버 판정 결과의 값만 쓴다.

AI 파트와의 관계
  기획안 v2 8장의 ★예외 설명·조치 생성은 AI(고도영 님) 기능이다. 이 모듈은
    (1) AI 모듈에 넘길 입력(요청 항목 목록)을 만드는 곳이고,
    (2) AI 모듈이 연결되기 전, 또는 실패했을 때 쓰는 템플릿 대체 문구다.
  GET /documents/{id}/follow-ups (v1.4안 4.22) 는 이 모듈의 build_follow_ups() 와 Drafter 를 쓴다 (followup_service).
  AI 문의 초안 모듈은 TemplateDrafter 와 같은 draft(supplier, lots) -> (제목, 본문) 형태로 만들어
  followup_service.get_drafter() 에 등록하면 된다.
  평가(규칙 베이스라인 vs AI 문의 초안 품질)에서 이 템플릿 결과가 베이스라인 역할도 한다.
"""
from dataclasses import dataclass, field

from app.core.enums import DocumentIssueCode as D, FollowUp, ReasonCode as R
from app.schemas.extraction import ExtractionResult

# 공급사에 요청해야 해결되는 사유 (나머지는 담당자가 내부에서 확인)
SUPPLIER_REASONS = {
    R.OUT_OF_SPEC, R.CONVERTED_OOS, R.BOUND_ABOVE_LIMIT, R.ND_NO_LOD, R.LOD_ABOVE_LIMIT,
    R.LOWER_LIMIT_UNVERIFIABLE, R.SPEC_COPIED, R.MISSING_REQUIRED, R.AMBIGUOUS_ANALYTE, R.SUM_ONLY,
}
SUPPLIER_ISSUES = {D.LOT_MISMATCH, D.PRODUCT_MISMATCH, D.DATE_CONFLICT, D.SUPPLIER_CONFLICT}

# 사유코드 → 화면·리포트용 짧은 이름 (기획안 v2 7.2)
REASON_LABELS = {
    R.OUT_OF_SPEC: "규격 초과",
    R.CONVERTED_OOS: "환산 후 규격 초과",
    R.BOUND_ABOVE_LIMIT: "보고 상한이 사내 상한보다 큼",
    R.ND_NO_LOD: "검출 안 됨, 검출한계 미기재",
    R.LOD_ABOVE_LIMIT: "검출한계가 사내 상한보다 큼",
    R.LOWER_LIMIT_UNVERIFIABLE: "하한 충족 여부 확인 불가",
    R.SPEC_COPIED: "결과 칸에 규격 문구 기재",
    R.MISSING_REQUIRED: "필수 항목 누락",
    R.AMBIGUOUS_ANALYTE: "측정 대상 모호(총량만 기재)",
    R.SUM_ONLY: "합산값만 기재",
    R.LOW_CONFIDENCE: "추출 신뢰도 낮음",
    R.UNMAPPED_ITEM: "미등록 항목명",
    R.UNPARSEABLE_VALUE: "값 해석 불가",
}
ISSUE_LABELS = {
    D.LOT_MISMATCH: "입고 로트와 CoA 로트 불일치",
    D.PRODUCT_MISMATCH: "입고 제품과 CoA 제품 불일치",
    D.DATE_CONFLICT: "날짜 충돌",
    D.SUPPLIER_CONFLICT: "공급사 판정 모순",
    D.SPEC_VERSION_UNKNOWN: "적용 규격 버전 불명",
}


@dataclass
class FollowUpLine:
    """후속 조치 1건 (항목 예외 또는 문서 정합성 오류)."""
    target: str              # 항목명, 또는 문서 정합성 오류면 "문서"
    code: str                # 사유코드 또는 문서 정합성 오류 코드
    label: str               # 짧은 이름 (REASON_LABELS)
    why: str                 # 왜 문제인가 (judgement_reason / issue message)
    condition: str           # 해결 조건 (resolution.condition)
    raw_value: str | None    # CoA 원문 값 (근거 인용용)
    to_supplier: bool        # 공급사 요청 대상인지


@dataclass
class FollowUps:
    supplier_lines: list[FollowUpLine] = field(default_factory=list)
    internal_lines: list[FollowUpLine] = field(default_factory=list)

    @property
    def all(self) -> list[FollowUpLine]:
        return self.supplier_lines + self.internal_lines


def build_follow_ups(result: ExtractionResult) -> FollowUps:
    """판정 결과 → 후속 조치 목록 (부적합 → 정합성 오류 → 판정 불가·누락·확인 필요 순)."""
    out = FollowUps()
    order = {"fail": 0, "undetermined": 2, "missing": 3, "check": 4}

    for issue in result.document_issues:
        line = FollowUpLine(target="문서", code=issue.code.value, label=ISSUE_LABELS.get(issue.code, issue.code),
                            why=issue.message, condition="올바른(최신) CoA 또는 공급사 확인", raw_value=None,
                            to_supplier=issue.code in SUPPLIER_ISSUES)
        (out.supplier_lines if line.to_supplier else out.internal_lines).append(line)

    exceptions = sorted((i for i in result.items if i.reason_code is not None),
                        key=lambda i: order.get(i.judgement.value, 9))
    for item in exceptions:
        line = FollowUpLine(
            target=item.normalized_name,
            code=item.reason_code.value,
            label=REASON_LABELS.get(item.reason_code, item.reason_code.value),
            why=item.judgement_reason or "",
            condition=item.resolution.condition if item.resolution else "",
            raw_value=item.raw_value,
            to_supplier=item.reason_code in SUPPLIER_REASONS,
        )
        (out.supplier_lines if line.to_supplier else out.internal_lines).append(line)
    # 부적합을 맨 앞에 두기 위해 공급사 요청만 다시 정렬 (문서 정합성 오류는 부적합 다음)
    out.supplier_lines.sort(key=lambda ln: 0 if ln.code in (R.OUT_OF_SPEC, R.CONVERTED_OOS) else
                            (1 if ln.target == "문서" else 2))
    return out


# 메일에 쓰는 공급사용 요청 문구. 해결 조건(resolution.condition)은 담당자용 문구라 그대로 쓰면 어색한 코드만 바꾼다.
SUPPLIER_REQUEST = {
    R.OUT_OF_SPEC: "단위·표기 오류 여부와 재시험 가능 여부 확인",
    R.CONVERTED_OOS: "산화물 기준 결과의 원소 기준 값 또는 단위·표기 확인",
    R.SPEC_COPIED: "실측값이 기재된 CoA 재발행",
    R.MISSING_REQUIRED: "해당 항목의 시험 결과(별도 성적서) 송부",
}

# 보류 화면의 후속 조치 기본값 추천 (명세 4.13 follow_up). 위에 있을수록 우선한다.
FOLLOW_UP_BY_CODE: list[tuple[set[str], FollowUp]] = [
    ({D.LOT_MISMATCH, D.PRODUCT_MISMATCH}, FollowUp.REQUEST_CORRECT_COA),
    ({R.SPEC_COPIED, D.DATE_CONFLICT}, FollowUp.REQUEST_REISSUE),
    ({R.ND_NO_LOD, R.LOD_ABOVE_LIMIT}, FollowUp.REQUEST_DETECTION_LIMIT),
    ({R.BOUND_ABOVE_LIMIT, R.LOWER_LIMIT_UNVERIFIABLE}, FollowUp.REQUEST_ACTUAL_VALUE),
    ({R.AMBIGUOUS_ANALYTE, R.SUM_ONLY}, FollowUp.REQUEST_SINGLE_VALUE),
    ({R.MISSING_REQUIRED}, FollowUp.INTERNAL_TEST),
]


def suggest_follow_up(follow_ups: FollowUps) -> FollowUp | None:
    """보류할 때 기본으로 고를 후속 조치. 공급사 요청이 없으면 None (부적합만 있으면 보류보다 처분 대상)."""
    codes = {ln.code for ln in follow_ups.supplier_lines}
    for group, follow_up in FOLLOW_UP_BY_CODE:
        if codes & {str(c) for c in group}:
            return follow_up
    return FollowUp.OTHER if follow_ups.internal_lines and not codes else None


def _request_lines(lines: list[FollowUpLine], start: int = 1) -> list[str]:
    """번호 붙은 요청 목록. 필수 항목 누락은 한 번호로 묶는다 (예: "K, Mg, 자성이물 시험 결과 송부")."""
    out: list[str] = []
    n = start - 1
    missing = [ln.target for ln in lines if ln.code == R.MISSING_REQUIRED]
    for ln in (ln for ln in lines if ln.code != R.MISSING_REQUIRED):
        n += 1
        cited = f' (CoA 기재: "{ln.raw_value}")' if ln.raw_value else ""
        out.append(f"{n}. {ln.target}{cited}")
        out.append(f"   - 사유: {ln.why or ln.label}")
        out.append(f"   - 요청: {SUPPLIER_REQUEST.get(ln.code, ln.condition)}")
    if missing:
        n += 1
        out.append(f"{n}. 당사 필수 시험 항목 중 CoA 에 없는 항목: {', '.join(missing)}")
        out.append(f"   - 요청: {SUPPLIER_REQUEST[R.MISSING_REQUIRED]}")
    return out


_CLOSING = [
    "",
    # 처분은 담당자가 정하므로 초안에서 보류·불합격 같은 처분을 단정하지 않는다
    "확인 후 회신 부탁드립니다.",
    "",
    "감사합니다.",
]


@dataclass
class LotRequest:
    """메일 초안 입력 1건 (로트 1개). AI 문의 초안 모듈에도 이 형식으로 넘긴다."""
    lot_no: str | None
    material_name: str | None
    lines: list[FollowUpLine]


def build_inquiry_draft(
    result: ExtractionResult, *, supplier: str | None, material_name: str | None, lot_no: str | None,
) -> tuple[str, str] | None:
    """로트 1건의 공급사 문의 메일 초안 (제목, 본문). 공급사에 요청할 것이 없으면 None."""
    lines = build_follow_ups(result).supplier_lines
    if not lines:
        return None
    return TemplateDrafter().draft(supplier, [LotRequest(lot_no, material_name, lines)])


class TemplateDrafter:
    """템플릿 기반 초안. AI 모듈이 연결되기 전 기본값이자, AI 실패 시 대체 문구."""
    source = "template"

    def draft(self, supplier: str | None, lots: list[LotRequest]) -> tuple[str, str]:
        supplier = supplier or "공급사"
        lots = [lot for lot in lots if lot.lines]
        material = next((lot.material_name for lot in lots if lot.material_name), None) or "원료"
        lot_names = [lot.lot_no or "로트번호 미기재" for lot in lots]

        if len(lots) == 1:
            subject = f"[CoA 확인 요청] {material} / Lot {lot_names[0]}"
            intro = (f"귀사에서 송부하신 {material} (Lot {lot_names[0]}) 시험성적서(CoA)를 검토하는 중 "
                     "아래 항목의 확인이 필요하여 요청드립니다.")
            body = [f"{supplier} 품질 담당자님께,", "", intro, "", *_request_lines(lots[0].lines), *_CLOSING]
            return subject, "\n".join(body)

        # 같은 공급사의 여러 로트를 메일 1통으로 묶는다 (기획안 v2 7.2: 같은 공급사 요청은 1통)
        subject = f"[CoA 확인 요청] {material} {len(lots)}개 로트 ({', '.join(lot_names)})"
        body = [f"{supplier} 품질 담당자님께,", "",
                f"귀사에서 송부하신 {material} 시험성적서(CoA) {len(lots)}건을 검토하는 중 "
                "아래 로트별 항목의 확인이 필요하여 요청드립니다.", ""]
        for lot, name in zip(lots, lot_names):
            body += [f"[Lot {name}]", *_request_lines(lot.lines), ""]
        return subject, "\n".join(body[:-1] + _CLOSING)
