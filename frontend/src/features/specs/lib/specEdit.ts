import type { SpecItem } from '../../review/shared/api/types';
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

/** 입력값 검증. 서버의 400 INVALID_SPEC_RANGE를 저장 전에 미리 막습니다. */
export function validateDraft(draft: SpecDraft): DraftError | null {
  const lsl = parseLimit(draft.lsl);
  const usl = parseLimit(draft.usl);
  if (lsl === 'invalid' || usl === 'invalid') return 'INVALID_NUMBER';
  if (draft.unit.trim() === '') return 'EMPTY_UNIT';
  if (lsl !== null && usl !== null && lsl > usl) return 'INVALID_SPEC_RANGE';
  return null;
}

const limitText = (value: number | null) => (value === null ? '-' : formatNumber(value));

export interface SpecChange {
  spec: SpecItem;
  body: { lsl: number | null; usl: number | null; unit: string };
  /** 변경 이력에 쓰는 문구. 예: "Ca USL 20 → 25 ppm" */
  descriptions: string[];
}

/** 원래 값과 입력값을 비교해 바뀐 행만 돌려줍니다. 검증을 통과하지 못한 행은 건너뜁니다. */
export function buildChanges(specs: SpecItem[], drafts: Record<number, SpecDraft>): SpecChange[] {
  const changes: SpecChange[] = [];
  for (const spec of specs) {
    const draft = drafts[spec.id];
    if (!draft || validateDraft(draft) !== null) continue;
    const lsl = parseLimit(draft.lsl) as number | null;
    const usl = parseLimit(draft.usl) as number | null;
    const unit = draft.unit.trim();
    const descriptions: string[] = [];
    if (lsl !== spec.lsl) descriptions.push(`${spec.item_name} LSL ${limitText(spec.lsl)} → ${limitText(lsl)} ${unit}`);
    if (usl !== spec.usl) descriptions.push(`${spec.item_name} USL ${limitText(spec.usl)} → ${limitText(usl)} ${unit}`);
    if (unit !== spec.unit) descriptions.push(`${spec.item_name} 단위 ${spec.unit} → ${unit}`);
    if (descriptions.length > 0) changes.push({ spec, body: { lsl, usl, unit }, descriptions });
  }
  return changes;
}

/** 입력값에 검증 오류가 있는 행의 id와 오류 */
export function draftErrors(drafts: Record<number, SpecDraft>): Record<number, DraftError> {
  const errors: Record<number, DraftError> = {};
  for (const [id, draft] of Object.entries(drafts)) {
    const error = validateDraft(draft);
    if (error) errors[Number(id)] = error;
  }
  return errors;
}
