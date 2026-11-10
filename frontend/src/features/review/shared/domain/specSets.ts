import type { SpecSet } from '../api/types';

/**
 * 검수 화면에 보이는 규격 세트 이름(코드 → 이름)과 순서. 원자재별로 보이는 세트와 그 순서를 이 상수 한 곳에서만 정합니다.
 * 서버의 세트 코드와 요청 값은 그대로이고 화면 표시만 바꿉니다. 여기에 없는 원자재는 서버 목록을 모두 보여 줍니다.
 */
export const SPEC_SET_NAMES_BY_MATERIAL: Readonly<Record<string, ReadonlyArray<{ code: string; name: string }>>> = {
  LI2CO3: [
    { code: 'LI2CO3-D1-2023', name: 'D1 · 기본' },
    { code: 'LI2CO3-D1-STRICT', name: 'D2 · 강화' },
    { code: 'LI2CO3-D1-RELAXED', name: 'D3 · 완화' },
  ],
};

/** 세트 코드의 화면 이름. 이름 맵에 없으면 null이라 호출하는 쪽이 서버 코드를 그대로 보여 줍니다. */
export function specSetName(code: string | null | undefined): string | null {
  if (!code) return null;
  for (const entries of Object.values(SPEC_SET_NAMES_BY_MATERIAL)) {
    const found = entries.find((entry) => entry.code === code);
    if (found) return found.name;
  }
  return null;
}

/**
 * 드롭다운에 보일 세트. 이름 맵이 있는 원자재는 맵의 세트만 맵의 순서로 보이고(서버 목록에 있는 것만),
 * 문서의 현재 세트가 맵에 없으면 선택값이 사라지지 않게 서버 코드 그대로 끝에 붙입니다. 맵이 없는 원자재는 서버 목록 전체입니다.
 */
export function visibleSpecSets(sets: SpecSet[], materialCode: string, currentCode: string | null): SpecSet[] {
  const entries = SPEC_SET_NAMES_BY_MATERIAL[materialCode];
  if (!entries) return sets;
  const shown = entries.flatMap((entry) => sets.filter((set) => set.code === entry.code));
  const current = currentCode ? sets.find((set) => set.code === currentCode) : undefined;
  return current && !shown.includes(current) ? [...shown, current] : shown;
}

/** 드롭다운 항목 이름. 이름 맵에 있으면 그 이름, 없으면 서버 코드(기본 세트는 "(기본)" 표시). */
export function specSetOptionLabel(set: SpecSet): string {
  return specSetName(set.code) ?? `${set.code}${set.is_default ? ' (기본)' : ''}`;
}
