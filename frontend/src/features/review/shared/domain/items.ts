import type { ExtractionItem, Judgement, ReviewLog } from '../api/types';
import { HIGH_CONFIDENCE_THRESHOLD, LOW_CONFIDENCE_THRESHOLD, REASON_NO_SPEC } from './constants';
import { formatNumber } from './format';

export type ConfidenceLevel = '높음' | '보통' | '낮음';

export function confidenceLevel(confidence: number | null): ConfidenceLevel | null {
  if (confidence === null) return null;
  if (confidence < LOW_CONFIDENCE_THRESHOLD) return '낮음';
  if (confidence < HIGH_CONFIDENCE_THRESHOLD) return '보통';
  return '높음';
}

export function isLowConfidence(item: Pick<ExtractionItem, 'confidence'>): boolean {
  return item.confidence !== null && item.confidence < LOW_CONFIDENCE_THRESHOLD;
}

/** 수정(edit) 또는 확인(confirm) 기록이 있는 항목. 항목의 reviewed와 같은 뜻이지만, 이력 줄 표시에 씁니다. */
export function processedItemIds(logs: ReviewLog[]): Set<string> {
  const ids = new Set<string>();
  for (const log of logs) {
    if (log.action === 'edit' || log.action === 'confirm') ids.add(log.item_id);
  }
  return ids;
}

/**
 * 사내 규격에 없어 참고로만 기록된 항목(reason_code가 없고 판정 근거가 "규격 없음"). 판정과 로트 권고에 쓰지 않습니다.
 * AI가 이름을 추정한 미등록 항목(UNMAPPED_ITEM)은 reason_code가 있어 참고 항목이 아닙니다.
 */
export function isReferenceItem(item: Pick<ExtractionItem, 'reason_code' | 'judgement_reason'>): boolean {
  return !item.reason_code && item.judgement_reason === REASON_NO_SPEC;
}

/**
 * 아직 확인하거나 수정하지 않은 신뢰도 낮음 항목 수(N). 서버가 처분 가능 여부를 판단하는 기준(항목의 reviewed)과 같습니다.
 * 누락 항목(confidence null)과 참고 항목(신뢰도가 낮아도 처분을 막지 않음)은 세지 않습니다. 신뢰도 낮음 배지는 그대로 보입니다.
 */
export function pendingLowConfidenceCount(items: ExtractionItem[]): number {
  return items.filter((item) => isLowConfidence(item) && !item.reviewed && !isReferenceItem(item)).length;
}

/** 항목마다 가장 최근 이력 */
export function latestLogByItem(logs: ReviewLog[]): Map<string, ReviewLog> {
  const map = new Map<string, ReviewLog>();
  for (const log of logs) map.set(log.item_id, log);
  return map;
}

export type ProcessedKind = 'edited' | 'verified' | null;

/** 이 항목의 처리 상태. 수정과 확인 중 가장 최근 것을 따릅니다. */
export function processedKind(itemId: string, logs: ReviewLog[]): ProcessedKind {
  let kind: ProcessedKind = null;
  for (const log of logs) {
    if (log.item_id !== itemId) continue;
    if (log.action === 'edit') kind = 'edited';
    else if (log.action === 'confirm') kind = 'verified';
  }
  return kind;
}

export function lastLog(itemId: string, logs: ReviewLog[], action: ReviewLog['action']): ReviewLog | undefined {
  let found: ReviewLog | undefined;
  for (const log of logs) {
    if (log.item_id === itemId && log.action === action) found = log;
  }
  return found;
}

/**
 * 시험 항목과 누락 항목으로 나눕니다. 규격 순서(specOrder: 규격 항목명 목록)대로 정렬하고,
 * 누락 항목은 하단에 묶습니다. 규격에 없는 항목은 각 그룹의 끝에 둡니다.
 */
export function splitItems(
  items: ExtractionItem[],
  specOrder: string[],
): { tests: ExtractionItem[]; missing: ExtractionItem[] } {
  const rank = (item: ExtractionItem) => {
    const index = specOrder.indexOf(item.normalized_name);
    return index === -1 ? Number.MAX_SAFE_INTEGER : index;
  };
  const byRank = (a: ExtractionItem, b: ExtractionItem) => rank(a) - rank(b);
  return {
    tests: items.filter((item) => item.judgement !== 'missing').sort(byRank),
    missing: items.filter((item) => item.judgement === 'missing').sort(byRank),
  };
}

/**
 * 항목의 값과 규격에 붙일 단위. 사내 규격 단위(spec_unit)를 먼저 쓰고, 없으면 CoA에서 읽은 단위(unit)를 씁니다.
 * 서버는 추출 단위(unit)를 비워 줄 수 있고, 값은 사내 규격 단위로 환산되어 있어 spec_unit이 맞는 단위입니다. 둘 다 없으면 null입니다.
 */
export function displayUnit(item: Pick<ExtractionItem, 'unit'> & { spec_unit?: string | null }): string | null {
  return item.spec_unit ?? item.unit ?? null;
}

/** 규격 표시. 예: ≥ 99.5 %, ≤ 50 ppm, 10–20 ppm */
export function formatSpec(item: Pick<ExtractionItem, 'spec_lsl' | 'spec_usl' | 'unit'> & { spec_unit?: string | null }): string {
  const shownUnit = displayUnit(item);
  const unit = shownUnit ? ` ${shownUnit}` : '';
  const { spec_lsl: lsl, spec_usl: usl } = item;
  if (lsl !== null && usl !== null) return `${formatNumber(lsl)}–${formatNumber(usl)}${unit}`;
  if (lsl !== null) return `≥ ${formatNumber(lsl)}${unit}`;
  if (usl !== null) return `≤ ${formatNumber(usl)}${unit}`;
  return '-';
}

const QUALIFIER_PREFIX: Record<string, string> = { less_than: '< ', less_equal: '≤ ' };

/** 사내 규격 단위로 환산한 값의 표시. 예: 100 ppm, < 100 ppm, N.D., 검출 안 됨 (검출한계 2 ppm) */
export function formatConverted(
  item: Pick<ExtractionItem, 'converted_value' | 'value_qualifier' | 'unit' | 'raw_value' | 'detection_limit'> & {
    spec_unit?: string | null;
  },
): string {
  const { converted_value: value, value_qualifier: qualifier, raw_value: raw, detection_limit: limit } = item;
  const unit = displayUnit(item);
  // 검출 안 됨: 검출한계를 받았으면 함께 보여 주고, 검출한계가 없으면 CoA 원문 그대로 보여 줍니다(시안 2-11, 2-12).
  if (qualifier === 'not_detected') {
    return limit !== null ? `검출 안 됨 (검출한계 ${formatNumber(limit)}${unit ? ` ${unit}` : ''})` : (raw ?? 'N.D.');
  }
  if (value === null || value === '') return raw ?? '-';
  if (typeof value === 'string') return value;
  const prefix = qualifier ? (QUALIFIER_PREFIX[qualifier] ?? '') : '';
  return `${prefix}${formatNumber(value)}${unit ? ` ${unit}` : ''}`;
}

function normalizeText(text: string): string {
  return text.replace(/\s+/g, '').replace(/=<|<=/g, '≤').toLowerCase();
}

/** 원문과 환산값이 다르면 "원문 0.01 % → 100 ppm" 형태로 보여 주기 위한 원문 문자열을 돌려줍니다. */
export function rawDifferent(item: ExtractionItem): string | null {
  if (!item.raw_value) return null;
  return normalizeText(item.raw_value) === normalizeText(formatConverted(item)) ? null : item.raw_value;
}

/** 수정 전 값(AI 추출값) 표시용. 항목의 단위(displayUnit)를 붙이고, 단위가 없으면 값만 돌려줍니다. */
export function withUnit(value: string | null, item: (Pick<ExtractionItem, 'unit'> & { spec_unit?: string | null }) | undefined): string {
  if (value === null) return '';
  const unit = item ? displayUnit(item) : null;
  // 실제 서버의 이력 값에는 단위가 이미 들어 있어("2.56 ppm") 한 번 더 붙이지 않습니다.
  if (!unit || value.toLowerCase().endsWith(unit.toLowerCase()) || value.includes('검출한계')) return value;
  return `${value} ${unit}`;
}

/**
 * 회신값 입력 박스의 재판정 미리보기(시안 2-12). 값 종류까지 보고 적합, 부적합, 판정 불가로 가늠합니다.
 * - 정량값: 사내 하한과 상한 범위 안이면 적합, 벗어나면 부적합
 * - "< 값", 검출 안 됨(검출한계): 사내 하한이 있으면 하한 충족 여부를 알 수 없어 판정 불가, 상한만 있으면 값이 상한 이하일 때 적합
 * 참고용이며 실제 판정은 서버가 PATCH 응답으로 돌려줍니다.
 */
export function previewReply(
  qualifier: 'exact' | 'less_than' | 'not_detected',
  value: number,
  lsl: number | null,
  usl: number | null,
): Extract<Judgement, 'pass' | 'fail' | 'undetermined'> {
  if (qualifier === 'exact') return previewJudgement(value, lsl, usl);
  if (lsl === null && usl === null) return 'pass';
  if (lsl !== null) return 'undetermined';
  return usl !== null && value <= usl ? 'pass' : 'undetermined';
}

/** "수정 후 판정" 미리보기. 참고용이며 실제 판정은 서버가 PATCH 응답으로 돌려줍니다. */
export function previewJudgement(
  value: number,
  lsl: number | null,
  usl: number | null,
): Extract<Judgement, 'pass' | 'fail'> {
  if (lsl !== null && value < lsl) return 'fail';
  if (usl !== null && value > usl) return 'fail';
  return 'pass';
}
