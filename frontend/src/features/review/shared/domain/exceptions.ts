import type { DocumentIssueCode, ReasonCode, ResolutionType, ValueSource } from '../api/types';

/**
 * [v1.4] 예외 사유코드, 해결 조건 종류, 문서 수준 문제, 값 출처의 한글 이름.
 * 사유코드와 문서 수준 문제 이름은 백엔드 inquiry_draft.py의 REASON_LABELS, ISSUE_LABELS와 같은 문구입니다(follow-ups 응답의 label과 같음).
 * 해결 조건 종류와 값 출처의 이름은 시안과 명세에 없어 값 이름을 풀어쓴 임시 표기입니다.
 */
export const REASON_CODE_LABEL: Record<ReasonCode, string> = {
  OUT_OF_SPEC: '규격 초과',
  CONVERTED_OOS: '환산 후 규격 초과',
  BOUND_ABOVE_LIMIT: '보고 상한이 사내 상한보다 큼',
  ND_NO_LOD: '검출 안 됨, 검출한계 미기재',
  LOD_ABOVE_LIMIT: '검출한계가 사내 상한보다 큼',
  LOWER_LIMIT_UNVERIFIABLE: '하한 충족 여부 확인 불가',
  SPEC_COPIED: '결과 칸에 규격 문구 기재',
  MISSING_REQUIRED: '필수 항목 누락',
  AMBIGUOUS_ANALYTE: '측정 대상 모호(총량만 기재)',
  SUM_ONLY: '합산값만 기재',
  LOW_CONFIDENCE: '추출 신뢰도 낮음',
  UNMAPPED_ITEM: '미등록 항목명',
  UNPARSEABLE_VALUE: '값 해석 불가',
};

export const RESOLUTION_TYPE_LABEL: Record<ResolutionType, string> = {
  actual_value: '실측값',
  detection_limit: '검출한계',
  single_value: '단일값',
  internal_test: '자체 시험값',
  confirm: '원문 확인',
};

/** 예외 상세 패널(시안 2-11)에서 해결 조건 종류를 "무엇을 받아야 하는지"로 보여 주는 이름 */
export const RESOLUTION_ACTION_LABEL: Record<ResolutionType, string> = {
  detection_limit: '검출한계 받기',
  actual_value: '실측값 받기',
  single_value: '개별값 받기',
  internal_test: '자체 시험값',
  confirm: '원문 확인',
};

export const DOCUMENT_ISSUE_LABEL: Record<DocumentIssueCode, string> = {
  LOT_MISMATCH: '입고 로트와 CoA 로트 불일치',
  PRODUCT_MISMATCH: '입고 제품과 CoA 제품 불일치',
  DATE_CONFLICT: '날짜 충돌',
  SUPPLIER_CONFLICT: '공급사 판정 모순',
  SPEC_VERSION_UNKNOWN: '적용 규격 버전 불명',
  SPEC_VERSION_MISMATCH: '적용 규격 버전 불일치',
  MULTI_LOT: '한 문서에서 로트가 2개 이상 읽힘, 담당자 확인 필요',
};

/** 담당자가 입력한 값의 출처. 첫 번째(correction)가 기본값입니다. */
export const VALUE_SOURCE_LABEL: Record<ValueSource, string> = {
  correction: '원문 오독 정정',
  supplier_reply: '공급사 회신값',
  internal_test: '자체 시험값',
};

export const VALUE_SOURCE_ORDER: ValueSource[] = ['correction', 'supplier_reply', 'internal_test'];
