import { LOW_CONFIDENCE_THRESHOLD, REASON_NO_SPEC } from '../../domain/constants';
import { emptySummary } from '../../domain/judgement';
import type {
  ApproveBody,
  DocumentStatus,
  ExtractionItem,
  FinalDecision,
  Judgement,
  JudgementSummary,
  LotRecommendation,
  ReasonCode,
  Resolution,
  SpecItem,
  ValueQualifier,
  ValueSource,
} from '../types';

/**
 * 목업 서버가 쓰는 규칙입니다. 백엔드(develop)의 판정 모듈을 옮겼습니다.
 *   - 사유코드 → 판정 5종: backend/app/services/judgement/policy.py (기본 정책)
 *   - 항목 판정: item_judge.py, 사유코드별 해결 조건: resolutions.py
 *   - 로트 권고: lot_recommend.py, 처분 검증: approval_service.py (명세 4.12)
 * 실제 화면은 이 규칙을 다시 계산하지 않고 서버(목업 포함) 응답을 따릅니다.
 * 옮기지 않은 것: 중금속 총량 → Pb 교차 규칙(cross_rules.py), 산화물 환산 계수, 정책 설정(.env)에 따른 판정 변경.
 */

/** 사유코드 → 판정 (백엔드 기본 정책). 부적합, 누락 코드는 고정입니다. */
const REASON_JUDGEMENT: Record<ReasonCode, Judgement> = {
  OUT_OF_SPEC: 'fail',
  CONVERTED_OOS: 'fail',
  MISSING_REQUIRED: 'missing',
  BOUND_ABOVE_LIMIT: 'undetermined',
  SPEC_COPIED: 'undetermined',
  SUM_ONLY: 'undetermined',
  LOD_ABOVE_LIMIT: 'undetermined',
  LOWER_LIMIT_UNVERIFIABLE: 'undetermined',
  ND_NO_LOD: 'check',
  AMBIGUOUS_ANALYTE: 'check',
  LOW_CONFIDENCE: 'check',
  UNMAPPED_ITEM: 'check',
  UNPARSEABLE_VALUE: 'check',
};

export function judgementForReason(code: ReasonCode | null): Judgement {
  return code === null ? 'pass' : REASON_JUDGEMENT[code];
}

/** 5 → "5 ppm", 0.4 → "0.4 %". 값이 없으면 "-". */
export function fmtValue(value: number | null, unit: string | null): string {
  if (value === null) return '-';
  return unit ? `${value} ${unit}` : String(value);
}

const limitText = (sym: string, value: number | null, unit: string | null, suffix = '') =>
  value === null ? '' : ` ${sym} ${fmtValue(value, unit)}${suffix}`;

/** 사유코드 1개 → 해결 조건 1개 (백엔드 resolutions.py) */
export function buildResolution(
  code: ReasonCode,
  itemName: string,
  spec: Pick<SpecItem, 'lsl' | 'usl' | 'unit'> | undefined,
  oxide: string | null = null,
): Resolution {
  const usl = spec?.usl ?? null;
  const lsl = spec?.lsl ?? null;
  const unit = spec?.unit ?? null;
  const target = itemName;
  switch (code) {
    case 'OUT_OF_SPEC':
      return { type: 'confirm', target_item: target, condition: '단위·표기 오류가 아님을 확인 (확인되면 부적합 확정)' };
    case 'CONVERTED_OOS':
      return { type: 'confirm', target_item: target, condition: `${oxide ?? '산화물'} → ${itemName} 환산 결과 확인 (확인되면 부적합 확정)` };
    case 'BOUND_ABOVE_LIMIT':
      return { type: 'actual_value', target_item: target, operator: '<=', threshold: usl, unit, condition: `정량값 또는 상한값${limitText('≤', usl, unit)} 보고` };
    case 'ND_NO_LOD':
    case 'LOD_ABOVE_LIMIT':
      return { type: 'detection_limit', target_item: target, operator: '<=', threshold: usl, unit, condition: `검출한계${limitText('≤', usl, unit)} (또는 정량값)` };
    case 'LOWER_LIMIT_UNVERIFIABLE':
      return { type: 'actual_value', target_item: target, operator: '>=', threshold: lsl, unit, condition: `정량값 (사내 하한${limitText('≥', lsl, unit)} 확인용)` };
    case 'SPEC_COPIED':
      return { type: 'actual_value', target_item: target, condition: '실측값이 적힌 CoA (결과 칸에 규격 문구가 적힘)' };
    case 'MISSING_REQUIRED':
      return { type: 'internal_test', target_item: target, condition: '별도 성적서 값 또는 자체 시험값 입력' };
    case 'AMBIGUOUS_ANALYTE':
      return { type: 'single_value', target_item: target, operator: '<=', threshold: usl, unit, condition: `${target} 단일 분석값${limitText('≤', usl, unit)}` };
    case 'SUM_ONLY':
      return { type: 'single_value', target_item: target, condition: `${target} 개별값` };
    case 'LOW_CONFIDENCE':
      return { type: 'confirm', target_item: target, condition: '원문 하이라이트와 대조해 값 확인' };
    case 'UNMAPPED_ITEM':
      return { type: 'confirm', target_item: target, condition: '사내 표준 항목명으로 수정하거나 참고 항목으로 확인' };
    case 'UNPARSEABLE_VALUE':
      return { type: 'confirm', target_item: target, condition: '원문 값을 확인해 수치로 입력' };
  }
}

/** 해석된 값. 담당자가 입력한 값(override)도 같은 모양입니다. */
export interface ParsedValue {
  qualifier: ValueQualifier | null;
  value: number | string | null;
  detectionLimit: number | null;
}

interface Verdict {
  code: ReasonCode | null;
  reason: string | null;
  deviation: number | null;
}

const ok = (reason: string | null = null): Verdict => ({ code: null, reason, deviation: null });
const problem = (code: ReasonCode, reason: string, deviation: number | null = null): Verdict => ({ code, reason, deviation });

/** 해석된 값 하나를 정량 규격과 비교합니다 (백엔드 judge_value). 검출한계 == 사내 상한은 적합입니다(기본 정책). */
function judgeValue(parsed: ParsedValue, spec: Pick<SpecItem, 'lsl' | 'usl' | 'unit'>, oxide: string | null): Verdict {
  const { lsl, usl, unit } = spec;
  const { qualifier, value } = parsed;

  if (qualifier === 'text') return problem('UNPARSEABLE_VALUE', '정량 항목인데 값이 문자열');
  if (lsl === null && usl === null) return ok('사내 규격 범위 미설정');

  if (qualifier === 'exact') {
    if (typeof value !== 'number' || Number.isNaN(value)) return problem('UNPARSEABLE_VALUE', '값 형식을 해석할 수 없음');
    const code: ReasonCode = oxide ? 'CONVERTED_OOS' : 'OUT_OF_SPEC';
    const via = oxide ? ` (${oxide} 환산)` : '';
    if (usl !== null && value > usl) return problem(code, `사내 상한 ${fmtValue(usl, unit)} 초과${via}`, Number((value - usl).toPrecision(12)));
    if (lsl !== null && value < lsl) return problem(code, `사내 하한 ${fmtValue(lsl, unit)} 미만${via}`, Number((value - lsl).toPrecision(12)));
    return ok();
  }

  if (qualifier === 'less_than' || qualifier === 'less_equal') {
    if (typeof value !== 'number' || Number.isNaN(value)) return problem('UNPARSEABLE_VALUE', '값 형식을 해석할 수 없음');
    const sym = qualifier === 'less_than' ? '<' : '≤';
    const shown = `상한값만 기재됨(${sym} ${fmtValue(value, unit)})`;
    // 하한이 있는 항목은 "< X"로는 하한을 충족하는지 알 수 없습니다.
    if (lsl !== null) return problem('LOWER_LIMIT_UNVERIFIABLE', `${shown}, 사내 하한 충족 여부 확인 불가`);
    if (usl !== null && value <= usl) return ok(`${shown}, 사내 상한 ${fmtValue(usl, unit)} 이하`);
    return problem('BOUND_ABOVE_LIMIT', `${shown}, 사내 상한 ${fmtValue(usl, unit)}보다 큼`);
  }

  if (qualifier === 'not_detected') {
    const dl = parsed.detectionLimit;
    if (dl === null) return problem('ND_NO_LOD', '검출한계 미기재');
    // 하한이 있는 항목은 "검출 안 됨"이 하한 충족을 뜻하지 않아 확인 필요가 아니라 판정 불가입니다.
    if (lsl !== null) return problem('LOWER_LIMIT_UNVERIFIABLE', `검출 안 됨(검출한계 ${fmtValue(dl, unit)}), 사내 하한이 있는 항목`);
    if (usl !== null && dl <= usl) return ok(`검출 안 됨(검출한계 ${fmtValue(dl, unit)})`);
    return problem('LOD_ABOVE_LIMIT', `검출한계 ${fmtValue(dl, unit)}가 사내 상한 ${fmtValue(usl, unit)}보다 큼`);
  }

  return problem('UNPARSEABLE_VALUE', '값 형식을 해석할 수 없음');
}

/** CoA 원문의 결과 칸이 규격 칸과 같은 문자열인지(실측값이 아님) */
export function isSpecTextAsResult(rawValue: string | null, rawSpec: string | null): boolean {
  if (!rawValue || !rawSpec) return false;
  const normalize = (text: string) => text.replace(/\s+/g, '').replace(/=<|<=/g, '≤').toLowerCase();
  return normalize(rawValue) === normalize(rawSpec);
}

/** 원문 이름이 산화물 표기(예: Na2O)이면 그 산화물을 돌려줍니다. 환산 후 규격 밖이면 CONVERTED_OOS입니다. */
function oxideOf(rawName: string | null): string | null {
  return /\b(Na2O|K2O|CaO|MgO|Fe2O3)\b/i.exec(rawName ?? '')?.[1] ?? null;
}

/** 담당자가 값을 입력해 둔 항목이면 그 값. 없으면 null */
export function currentOverride(item: ExtractionItem): ParsedValue | null {
  if (item.value_source === null) return null;
  return { qualifier: item.value_qualifier ?? 'exact', value: item.converted_value, detectionLimit: item.detection_limit };
}

export interface EvaluateOptions {
  /** 담당자가 확인(confirm)하거나 값을 입력했는지. 신뢰도 낮음 조건을 건너뜁니다. */
  reviewed?: boolean;
  /** 담당자가 입력한 값. 있으면 신뢰도 낮음, 규격 문구 복사, 값 해석 실패 검사를 건너뛰고 이 값으로 판정합니다. */
  override?: ParsedValue | null;
  valueSource?: ValueSource | null;
}

/**
 * 항목 1개를 규격에 대조해 서버 필드(판정, 사유코드, 해결 조건 등)를 채운 새 항목을 돌려줍니다 (백엔드 evaluate_item).
 * 판정 순서: 규격 없음, 정성, 누락, 신뢰도 낮음, 규격 문구 복사, 값 판정.
 * 목업 항목은 처음부터 해석된 값(value_qualifier, converted_value)을 갖고 있어, 값을 다시 해석하지 않고 그 값을 씁니다.
 */
export function evaluateItem(item: ExtractionItem, spec: SpecItem | undefined, options: EvaluateOptions = {}): ExtractionItem {
  const override = options.override ?? null;
  const reviewed = options.reviewed ?? false;
  const unit = spec ? spec.unit : item.unit;
  const parsed: ParsedValue | null =
    override ??
    (item.raw_value === null && item.mapping_source === 'spec'
      ? null
      : { qualifier: item.value_qualifier, value: item.converted_value, detectionLimit: item.detection_limit });
  const oxide = oxideOf(item.raw_name);

  let verdict: Verdict;
  if (!spec) {
    // 사내 규격에 없는 항목. AI가 이름을 추정했고 아직 확인하지 않았으면 UNMAPPED_ITEM(확인 필요)이고, 그 외에는 판정하지 않는 참고 항목입니다.
    // 참고 항목은 reason_code가 없어 신뢰도가 낮아도 처분을 막지 않습니다(isReferenceItem).
    verdict =
      item.mapping_source === 'ai' && override === null && !reviewed
        ? problem('UNMAPPED_ITEM', '사내 규격에 없는 항목명(AI 추정)')
        : ok(REASON_NO_SPEC);
  } else if (spec.spec_type === '정성') {
    verdict = ok('정성 항목, 판정 제외');
  } else if (parsed === null) {
    verdict = problem('MISSING_REQUIRED', 'CoA에 항목 없음');
  } else if (override === null && !reviewed && item.confidence !== null && item.confidence < LOW_CONFIDENCE_THRESHOLD) {
    verdict = problem('LOW_CONFIDENCE', `추출 신뢰도 낮음(${item.confidence.toFixed(2)})`);
  } else if (override === null && isSpecTextAsResult(item.raw_value, item.raw_spec)) {
    verdict = problem('SPEC_COPIED', '결과 칸이 규격 문구와 같음');
  } else {
    verdict = judgeValue(parsed, spec, override === null ? oxide : null);
  }

  return {
    ...item,
    unit,
    value_qualifier: parsed ? parsed.qualifier : null,
    converted_value: parsed ? parsed.value : null,
    detection_limit: parsed ? parsed.detectionLimit : null,
    spec_lsl: spec?.lsl ?? null,
    spec_usl: spec?.usl ?? null,
    judgement: judgementForReason(verdict.code),
    judgement_reason: verdict.reason,
    deviation: verdict.deviation,
    reason_code: verdict.code,
    resolution: verdict.code ? buildResolution(verdict.code, item.normalized_name, spec, override === null ? oxide : null) : null,
    reviewed: reviewed || override !== null,
    value_source: override !== null ? (options.valueSource ?? 'correction') : null,
  };
}

/** 저장된 항목을 담당자 검수 상태를 유지한 채 다시 판정합니다(항목명 수정, 규격 재판정). */
export function rejudgeItem(item: ExtractionItem, spec: SpecItem | undefined): ExtractionItem {
  return evaluateItem(item, spec, { reviewed: item.reviewed, override: currentOverride(item), valueSource: item.value_source });
}

/**
 * 로트 권고 (백엔드 lot_recommend.py). 부적합이 있으면 불합격 권고가 먼저이고,
 * 부적합이 없으면 문서 수준 문제(document_issues) 또는 판정 불가, 누락, 확인 필요가 하나라도 있을 때 보류입니다.
 */
export function recommendLot(summary: JudgementSummary, documentIssueCount = 0): LotRecommendation {
  if (summary.fail >= 1) return 'reject';
  if (documentIssueCount >= 1 || summary.undetermined + summary.missing + summary.check >= 1) return 'hold';
  return 'approve';
}

export function summarize(items: Array<Pick<ExtractionItem, 'judgement'>>): JudgementSummary {
  const summary = emptySummary();
  for (const item of items) summary[item.judgement] += 1;
  return summary;
}

/** 담당자 처분이 AI 권고와 같은지 (승인 권고 → 승인, 불합격 권고 → 불합격). 보류 권고에는 같은 처분이 없습니다. */
export function matchesRecommendation(decision: FinalDecision, recommendation: LotRecommendation): boolean {
  return (
    (decision === 'accept' && recommendation === 'approve') ||
    (decision === 'reject' && recommendation === 'reject')
  );
}

export type ApproveErrorCode =
  | 'ALREADY_APPROVED'
  | 'NOT_READY'
  | 'PENDING_LOW_CONFIDENCE_ITEMS'
  | 'INVALID_DECISION'
  | 'REASON_REQUIRED';

export interface ApproveCheckInput {
  status: DocumentStatus;
  recommendation: LotRecommendation;
  /** 확인하거나 수정하지 않은(reviewed가 아닌) 신뢰도 낮음 항목 수. 참고 항목(사내 규격에 없는 항목)은 세지 않습니다. */
  pendingLowConfidence: number;
  body: ApproveBody;
}

/** 명세 4.12의 처분(approve) 검증. 통과하면 null, 아니면 에러 코드를 돌려줍니다. */
export function checkApprove(input: ApproveCheckInput): ApproveErrorCode | null {
  const { status, recommendation, pendingLowConfidence, body } = input;
  if (status === 'approved') return 'ALREADY_APPROVED';
  if (status === 'queued' || status === 'processing' || status === 'failed') return 'NOT_READY';
  if (pendingLowConfidence > 0) return 'PENDING_LOW_CONFIDENCE_ITEMS';
  if (recommendation === 'reject' && body.decision === 'accept') return 'INVALID_DECISION';
  const reasonRequired =
    body.decision === 'conditional_accept' || !matchesRecommendation(body.decision, recommendation);
  if (reasonRequired && !(body.reason ?? '').trim()) return 'REASON_REQUIRED';
  return null;
}

/** 규격 수정 검증 (명세 4.21). 하한이 상한보다 크면 INVALID_SPEC_RANGE. */
export function checkSpecRange(lsl: number | null, usl: number | null): 'INVALID_SPEC_RANGE' | null {
  if (lsl !== null && usl !== null && lsl > usl) return 'INVALID_SPEC_RANGE';
  return null;
}
