import type { MappingEntry, MappingEntrySource } from '../../review/shared/api/Api';

export const SOURCE_LABEL: Record<MappingEntrySource, string> = {
  dictionary: '사전',
  ai: 'AI 추정',
  manual: '담당자 수정',
};

/** 표준 항목별 표기 개수. 키는 사내 표준 항목명입니다. */
export function countByStandard(entries: MappingEntry[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const entry of entries) counts[entry.standardName] = (counts[entry.standardName] ?? 0) + 1;
  return counts;
}

/**
 * 새 표기를 등록할 수 있는지. 같은 원문 표기가 이미 있으면 중복입니다
 * (매핑 사전은 협력사별이 아니라 material_code + raw_name 기준이라, 같은 원자재 안에서 표기는 하나만 둡니다).
 */
export function validateNewRawName(entries: MappingEntry[], rawName: string): 'EMPTY' | 'DUPLICATE' | null {
  const trimmed = rawName.trim();
  if (trimmed === '') return 'EMPTY';
  const exists = entries.some((entry) => entry.rawName.trim().toLowerCase() === trimmed.toLowerCase());
  return exists ? 'DUPLICATE' : null;
}

/**
 * "신규 누적" 표시 여부. 사전에 등록된 표기는 없고 담당자 수정(manual)으로만 쌓인 표준 항목입니다
 * (예: 검수 중 매핑을 고쳐서 처음 사전에 들어온 항목).
 */
export function isNewlyAccumulated(entries: MappingEntry[], standardName: string): boolean {
  const own = entries.filter((entry) => entry.standardName === standardName);
  return own.length > 0 && own.every((entry) => entry.source === 'manual');
}
