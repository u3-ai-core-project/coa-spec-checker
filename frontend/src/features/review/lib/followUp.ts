import type { ExtractionItem } from '../shared/api/types';

/** 후속 조치 줄을 펼칠 수 있는 판정인지 */
export function hasFollowUp(item: Pick<ExtractionItem, 'judgement'>): boolean {
  return item.judgement === 'undetermined' || item.judgement === 'missing';
}
