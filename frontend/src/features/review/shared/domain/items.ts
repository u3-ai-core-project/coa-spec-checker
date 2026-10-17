import type { ExtractionItem, Judgement, ReviewLog } from '../api/types';
import { HIGH_CONFIDENCE_THRESHOLD, LOW_CONFIDENCE_THRESHOLD } from './constants';
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

/** 수정(edit) 또는 확인(confirm) 기록이 있는 항목. 서버가 승인 가능 여부를 판단하는 기준과 같습니다. */
export function processedItemIds(logs: ReviewLog[]): Set<string> {
  const ids = new Set<string>();
  for (const log of logs) {
    if (log.action === 'edit' || log.action === 'confirm') ids.add(log.item_id);
  }
  return ids;
}

/** 아직 수정 또는 확인하지 않은 신뢰도 낮음 항목 수(N). 누락 항목(confidence null)은 세지 않습니다. */
export function pendingLowConfidenceCount(items: ExtractionItem[], logs: ReviewLog[]): number {
  const processed = processedItemIds(logs);
  return items.filter((item) => isLowConfidence(item) && !processed.has(item.item_id)).length;
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

/** 규격 표시. 예: ≥ 99.5 %, ≤ 50 ppm, 10–20 ppm */
export function formatSpec(item: Pick<ExtractionItem, 'spec_lsl' | 'spec_usl' | 'unit'>): string {
  const unit = item.unit ? ` ${item.unit}` : '';
  const { spec_lsl: lsl, spec_usl: usl } = item;
  if (lsl !== null && usl !== null) return `${formatNumber(lsl)}–${formatNumber(usl)}${unit}`;
  if (lsl !== null) return `≥ ${formatNumber(lsl)}${unit}`;
  if (usl !== null) return `≤ ${formatNumber(usl)}${unit}`;
  return '-';
}

const QUALIFIER_PREFIX: Record<string, string> = { less_than: '< ', less_equal: '≤ ' };

/** 사내 규격 단위로 환산한 값의 표시. 예: 100 ppm, < 100 ppm, 불검출(ND) */
export function formatConverted(
  item: Pick<ExtractionItem, 'converted_value' | 'value_qualifier' | 'unit' | 'raw_value'>,
): string {
  const { converted_value: value, value_qualifier: qualifier, unit, raw_value: raw } = item;
  if (qualifier === 'not_detected') return '불검출(ND)';
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

/** 수정 전 값(AI 추출값) 표시용. 단위가 없으면 값만 돌려줍니다. */
export function withUnit(value: string, unit: string | null): string {
  return unit ? `${value} ${unit}` : value;
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
