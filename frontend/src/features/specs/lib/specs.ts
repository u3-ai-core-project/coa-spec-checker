import type { SpecItem } from '../../review/shared/api/types';

export interface MaterialGroup {
  code: string;
  name: string;
  items: SpecItem[];
}

/** GET /specs 응답을 원자재별로 묶습니다. 원자재와 항목의 순서는 응답 순서를 따릅니다. */
export function groupByMaterial(specs: SpecItem[]): MaterialGroup[] {
  const groups = new Map<string, MaterialGroup>();
  for (const spec of specs) {
    let group = groups.get(spec.material_code);
    if (!group) {
      group = { code: spec.material_code, name: spec.material_name, items: [] };
      groups.set(spec.material_code, group);
    }
    group.items.push(spec);
  }
  return [...groups.values()];
}

/** 항목 중 가장 최근에 수정된 기록(수정 일시, 수정자). 수정 기록이 없으면 null입니다. */
export function latestUpdate(items: SpecItem[]): { at: string; by: string | null } | null {
  let latest: SpecItem | null = null;
  for (const item of items) {
    if (!item.updated_at) continue;
    if (!latest || new Date(item.updated_at).getTime() > new Date(latest.updated_at as string).getTime()) latest = item;
  }
  return latest && latest.updated_at ? { at: latest.updated_at, by: latest.updated_by } : null;
}

/** LSL/USL 칸 표시. 한계가 없으면 "-"입니다. */
export function formatLimit(value: number | null): string {
  return value === null ? '-' : String(value);
}
