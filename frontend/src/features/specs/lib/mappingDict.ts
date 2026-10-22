import type { MappingRecord, MappingRecordSource } from '../../review/shared/api/types';

export const SOURCE_LABEL: Record<MappingRecordSource, string> = {
  seed: '사전',
  manual: '담당자 수정',
};

/** 표준 항목별 표기 개수. 키는 사내 표준 항목명입니다. */
export function countByStandard(entries: MappingRecord[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const entry of entries) counts[entry.normalized_name] = (counts[entry.normalized_name] ?? 0) + 1;
  return counts;
}

/**
 * "신규 누적" 표시 여부. 기본 사전(seed)에는 없고 담당자 수정(manual)으로만 쌓인 표준 항목입니다
 * (예: 검수 중 매핑을 고쳐서 처음 사전에 들어온 항목).
 */
export function isNewlyAccumulated(entries: MappingRecord[], standardName: string): boolean {
  const own = entries.filter((entry) => entry.normalized_name === standardName);
  return own.length > 0 && own.every((entry) => entry.source === 'manual');
}
