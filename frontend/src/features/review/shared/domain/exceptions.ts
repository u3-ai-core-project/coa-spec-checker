import type { DocumentIssueCode, ReasonCode, ResolutionType } from '../api/types';

/**
 * [v1.4안] 예외 사유코드, 해결 조건 종류, 문서 수준 문제의 한글 이름.
 * 명세는 값 이름과 규칙 설명(2.3)만 있고 화면 문구가 없어, 규칙 설명을 줄여 쓴 임시 표기입니다.
 * TODO(디자인 협의): 시안이 나오면 문구를 맞춥니다.
 */
export const REASON_CODE_LABEL: Record<ReasonCode, string> = {
  OUT_OF_SPEC: '규격 이탈',
  CONVERTED_OOS: '환산 후 규격 이탈',
  BOUND_ABOVE_LIMIT: '상한값만 기재(사내 상한 초과)',
  ND_NO_LOD: '불검출, 검출한계 없음',
  SPEC_COPIED: '규격 문구를 결과로 기재',
  MISSING_REQUIRED: '필수 항목 누락',
  AMBIGUOUS_ANALYTE: '분석 대상 불명확',
  SUM_ONLY: '합산값만 기재',
  LOW_CONFIDENCE: '신뢰도 낮음',
  UNMAPPED_ITEM: '항목명 매핑 안 됨',
};

export const RESOLUTION_TYPE_LABEL: Record<ResolutionType, string> = {
  actual_value: '실측값',
  detection_limit: '검출한계',
  single_value: '단일값',
  internal_test: '자체 시험값',
  confirm: '원문 확인',
};

export const DOCUMENT_ISSUE_LABEL: Record<DocumentIssueCode, string> = {
  LOT_MISMATCH: '로트 불일치',
  PRODUCT_MISMATCH: '제품 불일치',
  DATE_CONFLICT: '날짜 충돌',
  SUPPLIER_CONFLICT: '협력사 불일치',
  SPEC_VERSION_UNKNOWN: '규격 버전 확인 불가',
};
