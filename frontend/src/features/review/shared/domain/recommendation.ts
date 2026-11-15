import type { FinalDecision, HoldFollowUp, LotRecommendation } from '../api/types';

/** 로트 권고(AI 권고). 시스템은 권고만 하고 최종 처분은 담당자가 결정합니다. */
export const RECOMMENDATION_META: Record<LotRecommendation, { label: string; color: string }> = {
  approve: { label: '승인 권고', color: '#177A46' },
  hold: { label: '보류 권고', color: '#5B616A' },
  reject: { label: '불합격 권고', color: '#C0342E' },
};

/** 담당자 처분 선택지. 보류는 처분이 아니라 on_hold 상태이지만 화면에서는 같은 선택지로 보여 줍니다. */
export type Disposition = FinalDecision | 'hold';

export const DISPOSITION_META: Record<Disposition, { label: string; color: string }> = {
  accept: { label: '승인', color: '#177A46' },
  conditional_accept: { label: '조건부 승인', color: '#9A5B00' },
  reject: { label: '불합격', color: '#C0342E' },
  hold: { label: '보류', color: '#5B616A' },
};

/** 처분 카드의 표시 순서 */
export const DISPOSITION_ORDER: Disposition[] = ['accept', 'conditional_accept', 'reject', 'hold'];

/** 로트 권고에 대응하는 처분. AI 권고 태그와 기본 선택에 씁니다. */
export function dispositionForRecommendation(rec: LotRecommendation): Disposition {
  if (rec === 'approve') return 'accept';
  if (rec === 'reject') return 'reject';
  return 'hold';
}

/**
 * 보류 후속 조치 이름. [v1.4안] request_single_value, request_reissue, request_correct_coa의 한글 이름은 시안에 없어
 * 명세의 값 이름을 풀어쓴 임시 표기입니다.
 */
export const FOLLOW_UP_LABEL: Record<HoldFollowUp, string> = {
  request_actual_value: '실측값 요청',
  request_detection_limit: '검출한계 요청',
  internal_test: '자체 시험',
  other: '기타',
  request_single_value: '단일값 요청',
  request_reissue: '재발행 요청',
  request_correct_coa: 'CoA 정정 요청',
};

/** 시안의 네 가지 뒤에 새 후속 조치를 이어 붙입니다. "기타"는 시안 위치(네 번째)를 지킵니다. */
export const FOLLOW_UP_ORDER: HoldFollowUp[] = [
  'request_actual_value',
  'request_detection_limit',
  'internal_test',
  'other',
  'request_single_value',
  'request_reissue',
  'request_correct_coa',
];

export function followUpLabel(value: string | null): string {
  if (!value) return '';
  return FOLLOW_UP_LABEL[value as HoldFollowUp] ?? value;
}

/** 문서의 담당자 처분 표시. 최종 처분이 있으면 그것을, 보류 상태면 "보류"를, 아니면 null을 돌려줍니다. */
export function dispositionOf(doc: { final_decision: FinalDecision | null; status: string }): Disposition | null {
  if (doc.final_decision) return doc.final_decision;
  return doc.status === 'on_hold' ? 'hold' : null;
}
