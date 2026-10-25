"""[담당: 장수민] 상태·판정·처분·사유코드 enum (명세 2.1, 2.6, 2.7, 2.8, v1.4안).

str 을 상속하므로 JSON 직렬화 시 값 문자열 그대로 나간다.
DB 에는 native enum 이 아닌 VARCHAR + CHECK 로 저장한다 (값 추가 시 마이그레이션이 단순).
"""
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    USER = "USER"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    IN_REVIEW = "in_review"
    ON_HOLD = "on_hold"
    APPROVED = "approved"
    FAILED = "failed"


# 검수/처분이 가능한 상태 (그 외는 409 NOT_READY 또는 ALREADY_APPROVED)
REVIEWABLE_STATUSES = {DocumentStatus.EXTRACTED, DocumentStatus.IN_REVIEW, DocumentStatus.ON_HOLD}
NOT_READY_STATUSES = {DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.FAILED}


class ReviewStatus(StrEnum):
    """JSON 의 review_status. AI 파트 호환용. 기준은 documents.status (명세 2.1)."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    ON_HOLD = "on_hold"
    APPROVED = "approved"


class Judgement(StrEnum):
    PASS = "pass"                  # 적합
    FAIL = "fail"                  # 부적합
    UNDETERMINED = "undetermined"  # 판정 불가
    MISSING = "missing"            # 누락
    CHECK = "check"                # 확인 필요


class ReasonCode(StrEnum):
    """예외 사유코드 (명세 v1.4안 2.1). 서버 규칙이 채운다.

    판정 5종은 사유코드에서 따라 나온다. 사유코드 → 판정 대응은 app/services/judgement/policy.py 의 정책 표에서 정한다.
    적합(pass) 항목은 사유코드가 없다(null).
    """
    # ---- v1.4안 목록 ----
    OUT_OF_SPEC = "OUT_OF_SPEC"                # 실측값이 사내 규격 밖 → 부적합 (고정)
    CONVERTED_OOS = "CONVERTED_OOS"            # 산화물 환산 후 규격 밖 → 부적합 (고정)
    BOUND_ABOVE_LIMIT = "BOUND_ABOVE_LIMIT"    # "< X" 인데 X 가 사내 상한보다 큼
    ND_NO_LOD = "ND_NO_LOD"                    # 검출 안 됨, 검출한계 미기재
    SPEC_COPIED = "SPEC_COPIED"                # 결과 칸 = 규격 문구
    MISSING_REQUIRED = "MISSING_REQUIRED"      # 사내 필수 항목이 CoA 에 없음 → 누락 (고정)
    AMBIGUOUS_ANALYTE = "AMBIGUOUS_ANALYTE"    # 측정 대상 모호 (예: 중금속 총량만 있어 Pb 를 알 수 없음)
    SUM_ONLY = "SUM_ONLY"                      # 합산값만 있음 (예: Na+K) — 규칙은 아직 없음, 자리만 둠
    LOW_CONFIDENCE = "LOW_CONFIDENCE"          # 추출 신뢰도 기준값 미만
    UNMAPPED_ITEM = "UNMAPPED_ITEM"            # AI 가 추정한 항목명이 사내 규격과 맞지 않음 (정책 설정 시)
    # ---- v1.4안 목록 외 추가 (기존 판정 분기에 대응하는 코드가 없어 추가. 명세 반영 필요) ----
    LOD_ABOVE_LIMIT = "LOD_ABOVE_LIMIT"                    # 검출 안 됨인데 검출한계가 사내 상한보다 큼
    LOWER_LIMIT_UNVERIFIABLE = "LOWER_LIMIT_UNVERIFIABLE"  # 하한이 있는 항목에 "< X" 또는 검출 안 됨
    UNPARSEABLE_VALUE = "UNPARSEABLE_VALUE"                # 값 해석 실패, 단위 환산 불가, 정량 항목에 문자열


class ResolutionType(StrEnum):
    """해결 조건 종류 (명세 v1.4안 2.1 resolution.type)."""
    ACTUAL_VALUE = "actual_value"        # 실측값(정량값) 받기
    DETECTION_LIMIT = "detection_limit"  # 검출한계 받기
    SINGLE_VALUE = "single_value"        # 합산·총량이 아닌 개별 항목값 받기
    INTERNAL_TEST = "internal_test"      # 자체 시험값 또는 별도 성적서 값
    CONFIRM = "confirm"                  # 담당자 확인 (원문 대조, 환산·표기 확인)


class DocumentIssueCode(StrEnum):
    """문서 정합성 오류 (명세 v1.4안 2.1 document_issues). 1개 이상이면 보류 권고.

    탐지 규칙: app/services/judgement/document_checks.py (LOT_MISMATCH, DATE_CONFLICT, SPEC_VERSION_UNKNOWN),
    app/services/batch_service.link_by_lot (일괄 접수: LOT_MISMATCH, PRODUCT_MISMATCH = 입고 원자재 다름).
    CoA 제품명(product_name) 비교와 SUPPLIER_CONFLICT 는 아직 탐지하지 않는다.
    """
    LOT_MISMATCH = "LOT_MISMATCH"
    PRODUCT_MISMATCH = "PRODUCT_MISMATCH"
    DATE_CONFLICT = "DATE_CONFLICT"
    SUPPLIER_CONFLICT = "SUPPLIER_CONFLICT"
    SPEC_VERSION_UNKNOWN = "SPEC_VERSION_UNKNOWN"


class LotRecommendation(StrEnum):
    APPROVE = "approve"
    HOLD = "hold"
    REJECT = "reject"


class FinalDecision(StrEnum):
    ACCEPT = "accept"
    CONDITIONAL_ACCEPT = "conditional_accept"
    REJECT = "reject"


class ValueQualifier(StrEnum):
    EXACT = "exact"
    LESS_THAN = "less_than"
    LESS_EQUAL = "less_equal"
    NOT_DETECTED = "not_detected"
    TEXT = "text"


class MappingSource(StrEnum):
    """추출 결과 JSON 항목의 mapping_source."""
    DICTIONARY = "dictionary"
    AI = "ai"
    MANUAL = "manual"
    SPEC = "spec"  # 서버가 만든 누락 항목


class ItemMappingSource(StrEnum):
    """item_mappings 테이블의 source."""
    SEED = "seed"
    MANUAL = "manual"


class SpecType(StrEnum):
    QUANTITATIVE = "정량"
    QUALITATIVE = "정성"


class ReviewAction(StrEnum):
    EDIT = "edit"
    CONFIRM = "confirm"
    RENAME = "rename"


class ValueSource(StrEnum):
    """담당자가 입력한 값의 출처 (v1.4안, 검수 API PATCH 의 value_source). review_logs 와 결과 JSON 에 남긴다.

    같은 "값 수정"이라도 원문 오독을 고친 것인지, 공급사 회신값인지, 자체 시험값인지에 따라
    리포트·감사 이력의 의미가 다르기 때문에 구분한다.
    """
    CORRECTION = "correction"          # 원문을 보고 추출값을 바로잡음 (기본값)
    SUPPLIER_REPLY = "supplier_reply"  # 공급사 회신값 (실측값, 검출한계, 개별값)
    INTERNAL_TEST = "internal_test"    # 자체 시험값 또는 별도 성적서 값


class ApprovalAction(StrEnum):
    APPROVE = "approve"
    HOLD = "hold"
    CANCEL = "cancel"


class FollowUp(StrEnum):
    """보류 시 후속 조치 (명세 4.13, v1.4안에서 3개 추가)."""
    REQUEST_ACTUAL_VALUE = "request_actual_value"        # 협력사 실측값 요청 (BOUND_ABOVE_LIMIT 등)
    REQUEST_DETECTION_LIMIT = "request_detection_limit"  # 검출한계 요청 (ND_NO_LOD)
    INTERNAL_TEST = "internal_test"                      # 자체 시험 (MISSING_REQUIRED)
    REQUEST_SINGLE_VALUE = "request_single_value"        # v1.4안: 개별값 요청 (AMBIGUOUS_ANALYTE, SUM_ONLY)
    REQUEST_REISSUE = "request_reissue"                  # v1.4안: CoA 재발행 요청 (SPEC_COPIED, DATE_CONFLICT)
    REQUEST_CORRECT_COA = "request_correct_coa"          # v1.4안: 올바른 CoA 요청 (LOT_MISMATCH, PRODUCT_MISMATCH)
    OTHER = "other"


def status_to_review_status(status: DocumentStatus) -> ReviewStatus:
    """documents.status 변경 시 JSON review_status 동기화용 (명세 2.1)."""
    return {
        DocumentStatus.IN_REVIEW: ReviewStatus.IN_REVIEW,
        DocumentStatus.ON_HOLD: ReviewStatus.ON_HOLD,
        DocumentStatus.APPROVED: ReviewStatus.APPROVED,
    }.get(status, ReviewStatus.PENDING)
