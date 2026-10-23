import type { SpecChangeLog, SpecItem } from '../../review/shared/api/types';
import { formatNumber } from '../../review/shared/domain/format';

/** 편집 중인 한 행의 입력값. PATCH /specs/{id}가 받는 세 필드(lsl, usl, unit)만 수정할 수 있습니다. */
export interface SpecDraft {
  lsl: string;
  usl: string;
  unit: string;
}

export function draftOf(spec: SpecItem): SpecDraft {
  return {
    lsl: spec.lsl === null ? '' : String(spec.lsl),
    usl: spec.usl === null ? '' : String(spec.usl),
    unit: spec.unit ?? '',
  };
}

/** 한계 입력값을 숫자로 바꿉니다. 비어 있으면 null(한계 없음), 숫자가 아니면 'invalid'입니다. */
export function parseLimit(text: string): number | null | 'invalid' {
  const normalized = text.replace(/,/g, '').trim();
  if (normalized === '') return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : 'invalid';
}

export type DraftError = 'INVALID_NUMBER' | 'INVALID_SPEC_RANGE' | 'EMPTY_UNIT';

export const DRAFT_ERROR_MESSAGE: Record<DraftError, string> = {
  INVALID_NUMBER: '숫자로 입력해 주십시오.',
  INVALID_SPEC_RANGE: '하한은 상한보다 클 수 없습니다.',
  EMPTY_UNIT: '단위를 입력해 주십시오.',
};

/** 입력값 검증. 서버의 400 INVALID_SPEC_RANGE를 저장 전에 미리 막습니다. 원래 단위가 없는 항목(정성 항목 등)은 빈 단위를 허용합니다. */
export function validateDraft(draft: SpecDraft, originalUnit: string | null): DraftError | null {
  const lsl = parseLimit(draft.lsl);
  const usl = parseLimit(draft.usl);
  if (lsl === 'invalid' || usl === 'invalid') return 'INVALID_NUMBER';
  if (draft.unit.trim() === '' && (originalUnit ?? '').trim() !== '') return 'EMPTY_UNIT';
  if (lsl !== null && usl !== null && lsl > usl) return 'INVALID_SPEC_RANGE';
  return null;
}

const limitText = (value: number | null) => (value === null ? '-' : formatNumber(value));

export interface SpecChange {
  spec: SpecItem;
  body: { lsl: number | null; usl: number | null; unit: string | null };
  /** 변경 이력에 쓰는 문구. 예: "Ca USL 20 → 25 ppm" */
  descriptions: string[];
}

/** 원래 값과 입력값을 비교해 바뀐 행만 돌려줍니다. 검증을 통과하지 못한 행은 건너뜁니다. */
export function buildChanges(specs: SpecItem[], drafts: Record<number, SpecDraft>): SpecChange[] {
  const changes: SpecChange[] = [];
  for (const spec of specs) {
    const draft = drafts[spec.id];
    if (!draft || validateDraft(draft, spec.unit) !== null) continue;
    const lsl = parseLimit(draft.lsl) as number | null;
    const usl = parseLimit(draft.usl) as number | null;
    const unit = draft.unit.trim();
    const before = spec.unit ?? '';
    const descriptions: string[] = [];
    if (lsl !== spec.lsl) descriptions.push(`${spec.item_name} LSL ${limitText(spec.lsl)} → ${limitText(lsl)} ${unit}`);
    if (usl !== spec.usl) descriptions.push(`${spec.item_name} USL ${limitText(spec.usl)} → ${limitText(usl)} ${unit}`);
    if (unit !== before) descriptions.push(`${spec.item_name} 단위 ${before || '없음'} → ${unit || '없음'}`);
    if (descriptions.length > 0) changes.push({ spec, body: { lsl, usl, unit: unit === '' ? null : unit }, descriptions });
  }
  return changes;
}

/** 입력값에 검증 오류가 있는 행의 id와 오류 */
export function draftErrors(specs: SpecItem[], drafts: Record<number, SpecDraft>): Record<number, DraftError> {
  const errors: Record<number, DraftError> = {};
  for (const spec of specs) {
    const draft = drafts[spec.id];
    if (!draft) continue;
    const error = validateDraft(draft, spec.unit);
    if (error) errors[spec.id] = error;
  }
  return errors;
}

/** 변경 이력 한 건에 항목 정보를 붙인 것. 서버 응답에는 항목 이름이 없어 항목(규격 id)마다 불러 온 화면이 붙입니다. */
export interface SpecChangeEntry extends SpecChangeLog {
  spec_id: number;
  item_name: string;
  unit: string | null;
}

const FIELD_LABEL: Record<string, string> = { lsl: 'LSL', usl: 'USL', unit: '단위' };

/** "lsl: 없음, usl: 30" → [["lsl", "없음"], ["usl", "30"]]. "필드: 값" 모양이 아니면 키를 빈 문자열로 둡니다. */
function parsePairs(text: string): Array<[string, string]> {
  return text.split(', ').map((part): [string, string] => {
    const at = part.indexOf(': ');
    return at === -1 ? ['', part] : [part.slice(0, at), part.slice(at + 2)];
  });
}

/**
 * 규격 변경 이력 한 건을 "USL 50 → 30 ppm" 같은 문구로 만듭니다.
 * 서버는 실제로 바뀐 필드만 "usl: 50" → "usl: 30" 문자열로 줍니다(여러 필드면 ", "로 이음, 값이 없으면 "없음").
 * 모양을 풀 수 없으면 서버 문자열을 그대로 "이전 → 이후"로 보여 줍니다.
 */
export function describeChangeLog(log: SpecChangeLog, unit: string | null): string {
  const before = parsePairs(log.before_value);
  const after = parsePairs(log.after_value);
  const readable = before.length === after.length && before.every(([key], index) => key !== '' && key === after[index][0]);
  if (!readable) return `${log.before_value} → ${log.after_value}`;
  return before
    .map(([key, from], index) => {
      const to = after[index][1];
      const suffix = (key === 'lsl' || key === 'usl') && unit && to !== '없음' ? ` ${unit}` : '';
      return `${FIELD_LABEL[key] ?? key} ${from} → ${to}${suffix}`;
    })
    .join(', ');
}
