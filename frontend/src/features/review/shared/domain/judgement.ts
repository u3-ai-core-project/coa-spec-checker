import type { Judgement, JudgementSummary } from '../api/types';

export interface JudgementMeta {
  label: string;
  /** 글자색 */
  color: string;
  /** 배경색 */
  bg: string;
}

/** 항목 판정 5종. 판정마다 색상 하나로 고정하고, 색상과 텍스트를 함께 표시합니다. */
export const JUDGEMENT_META: Record<Judgement, JudgementMeta> = {
  pass: { label: '적합', color: '#177A46', bg: '#E7F5EC' },
  fail: { label: '부적합', color: '#C0342E', bg: '#FBEAE9' },
  undetermined: { label: '판정 불가', color: '#6B4FBB', bg: '#F0ECFA' },
  missing: { label: '누락', color: '#5B616A', bg: '#EEF0F3' },
  check: { label: '확인 필요', color: '#9A5B00', bg: '#FBF0DF' },
};

/** 건수 칩과 요약 칸의 표시 순서 */
export const JUDGEMENT_ORDER: Judgement[] = ['pass', 'fail', 'undetermined', 'missing', 'check'];

/** 주요색 */
export const PRIMARY_COLOR = '#2B4FCB';

export function sumSummary(summary: JudgementSummary): number {
  return JUDGEMENT_ORDER.reduce((total, key) => total + summary[key], 0);
}

export function emptySummary(): JudgementSummary {
  return { pass: 0, fail: 0, undetermined: 0, missing: 0, check: 0 };
}
