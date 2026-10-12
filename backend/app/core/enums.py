"""[담당: 장수민] 상태·판정·처분 enum (명세 2.1, 2.6, 2.7, 2.8).

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


class ApprovalAction(StrEnum):
    APPROVE = "approve"
    HOLD = "hold"
    CANCEL = "cancel"


class FollowUp(StrEnum):
    REQUEST_ACTUAL_VALUE = "request_actual_value"
    REQUEST_DETECTION_LIMIT = "request_detection_limit"
    INTERNAL_TEST = "internal_test"
    OTHER = "other"


def status_to_review_status(status: DocumentStatus) -> ReviewStatus:
    """documents.status 변경 시 JSON review_status 동기화용 (명세 2.1)."""
    return {
        DocumentStatus.IN_REVIEW: ReviewStatus.IN_REVIEW,
        DocumentStatus.ON_HOLD: ReviewStatus.ON_HOLD,
        DocumentStatus.APPROVED: ReviewStatus.APPROVED,
    }.get(status, ReviewStatus.PENDING)
