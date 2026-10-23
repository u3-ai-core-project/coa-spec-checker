import { MOCK_MAPPING_CANDIDATES, type MappingOption } from '../shared/api/mock/mappingCandidates';
import type { SpecItem } from '../shared/api/types';
import { USE_MOCK } from '../shared/config';

/** 목업 모드에서만 규격 외에 시안의 후보(중금속 총량, Pb, As, Cd)를 더 보여 줍니다. */
export const EXTRA_MAPPING_OPTIONS: readonly MappingOption[] = USE_MOCK ? MOCK_MAPPING_CANDIDATES : [];

/**
 * 매핑 수정 다이얼로그에 보여 줄 선택지. 규격 항목(이름, 단위)에 목업 후보를 더하고, 검색어는 이름, 보조 표기, 키워드에서
 * 찾습니다(대소문자 구분 없음). 후보는 규격 항목과 이름이 겹치지 않는 것만 더하고, 검색어가 있으면 후보를 앞에 둡니다.
 */
export function buildMappingOptions(specs: SpecItem[], query: string, extra: readonly MappingOption[] = EXTRA_MAPPING_OPTIONS): MappingOption[] {
  const needle = query.trim().toLowerCase();
  const fromSpecs: MappingOption[] = specs.map((spec) => ({ name: spec.item_name, note: spec.unit ?? '' }));
  const specNames = new Set(fromSpecs.map((option) => option.name));
  const candidates = extra.filter((option) => !specNames.has(option.name));
  const matches = (option: MappingOption) =>
    [option.name, option.note, `${option.name} ${option.note}`, ...(option.keywords ?? [])].some((text) => text.toLowerCase().includes(needle));
  if (!needle) return [...fromSpecs, ...candidates];
  return [...candidates.filter(matches), ...fromSpecs.filter(matches)];
}
