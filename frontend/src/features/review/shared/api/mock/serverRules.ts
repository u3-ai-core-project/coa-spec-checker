import { LOW_CONFIDENCE_THRESHOLD } from '../../domain/constants';
import { emptySummary } from '../../domain/judgement';
import { formatNumber } from '../../domain/format';
import type {
  ApproveBody,
  DocumentStatus,
  ExtractionItem,
  FinalDecision,
  Judgement,
  JudgementSummary,
  LotRecommendation,
  SpecItem,
  ValueQualifier,
} from '../types';

/**
 * 목업 서버가 쓰는 규칙입니다. 명세 2.3(항목 판정), 2.4(로트 권고), 4.12(처분 검증)를 그대로 옮겼습니다.
 * 실제 화면은 이 규칙을 다시 계산하지 않고 서버(목업 포함) 응답을 따릅니다.
 * 이 파일의 함수는 vitest로 검증합니다.
 */

export interface JudgeInput {
  qualifier: ValueQualifier | null;
  value: number | string | null;
  detectionLimit: number | null;
  unit: string | null;
  lsl: number | null;
  usl: number | null;
  /** 사내 규격에 있는 항목인지. 없으면 판정하지 않습니다. */
  hasSpec: boolean;
  /** 정성 항목은 판정하지 않습니다. */
  qualitative: boolean;
  confidence: number | null;
  /** 담당자가 수정(edit)하거나 확인(confirm)했으면 신뢰도 조건을 빼고 값만으로 판정합니다. */
  resolved: boolean;
  /** 결과 칸이 규격 문구와 같은 문자열인지(실측값이 아님) */
  resultSameAsSpec: boolean;
}

export interface JudgeOutput {
  judgement: Judgement;
  reason: string | null;
  deviation: number | null;
}

const withUnit = (value: number, unit: string | null) => `${formatNumber(value)}${unit ? ` ${unit}` : ''}`;

/** 명세 2.3의 항목 판정 규칙 */
export function judgeItem(input: JudgeInput): JudgeOutput {
  const { qualifier, value, detectionLimit, unit, lsl, usl } = input;

  // 사내 규격에 없는 항목 또는 정성 항목: 판정하지 않고 pass + "규격 없음"
  if (!input.hasSpec || input.qualitative) {
    return { judgement: 'pass', reason: '규격 없음', deviation: null };
  }

  // 신뢰도 낮음: 값 판정보다 우선 (담당자가 수정·확인하기 전까지)
  if (!input.resolved && input.confidence !== null && input.confidence < LOW_CONFIDENCE_THRESHOLD) {
    return {
      judgement: 'check',
      reason: `신뢰도가 기준값(${LOW_CONFIDENCE_THRESHOLD}) 미만입니다.`,
      deviation: null,
    };
  }

  // 결과 칸이 규격 문구와 같음(실측값 아님)
  if (input.resultSameAsSpec) {
    return { judgement: 'undetermined', reason: '결과 칸이 규격 문구와 같음', deviation: null };
  }

  if (qualifier === 'not_detected') {
    if (detectionLimit === null) {
      return { judgement: 'check', reason: '검출한계 미기재', deviation: null };
    }
    if (usl !== null && detectionLimit <= usl) {
      return { judgement: 'pass', reason: null, deviation: null };
    }
    return {
      judgement: 'undetermined',
      reason: `검출한계(${withUnit(detectionLimit, unit)})가 사내 상한보다 큼`,
      deviation: null,
    };
  }

  if (typeof value !== 'number' || Number.isNaN(value)) {
    return { judgement: 'check', reason: '값을 해석할 수 없음', deviation: null };
  }

  if (qualifier === 'less_than' || qualifier === 'less_equal') {
    const mark = qualifier === 'less_than' ? '<' : '≤';
    if (usl !== null && value <= usl) {
      return { judgement: 'pass', reason: null, deviation: null };
    }
    return {
      judgement: 'undetermined',
      reason:
        usl === null
          ? `상한값만 기재됨(${mark} ${withUnit(value, unit)}), 하한을 확인할 수 없음`
          : `상한값만 기재됨(${mark} ${withUnit(value, unit)}), 사내 상한 ${withUnit(usl, unit)}보다 큼`,
      deviation: null,
    };
  }

  // exact
  if (lsl !== null && value < lsl) {
    return { judgement: 'fail', reason: `사내 하한 ${withUnit(lsl, unit)} 미만`, deviation: round(lsl - value) };
  }
  if (usl !== null && value > usl) {
    return { judgement: 'fail', reason: `사내 상한 ${withUnit(usl, unit)} 초과`, deviation: round(value - usl) };
  }
  return { judgement: 'pass', reason: null, deviation: null };
}

function round(n: number): number {
  return Number(n.toFixed(6));
}

/** 명세 2.4의 로트 권고 규칙 */
export function recommendLot(summary: JudgementSummary): LotRecommendation {
  if (summary.fail >= 1) return 'reject';
  if (summary.undetermined + summary.missing + summary.check >= 1) return 'hold';
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
  /** 수정 또는 확인 기록이 없는 신뢰도 낮음 항목 수 */
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

/** 항목을 규격에 대조해 다시 판정합니다. 목업 서버가 PATCH와 confirm에서 씁니다. */
export function rejudge(
  item: ExtractionItem,
  spec: SpecItem | undefined,
  resolved: boolean,
  resultSameAsSpec: boolean,
): ExtractionItem {
  const result = judgeItem({
    qualifier: item.value_qualifier,
    value: item.converted_value,
    detectionLimit: item.detection_limit,
    unit: spec?.unit ?? item.unit,
    lsl: spec?.lsl ?? null,
    usl: spec?.usl ?? null,
    hasSpec: spec !== undefined,
    qualitative: spec?.spec_type === '정성',
    confidence: item.confidence,
    resolved,
    resultSameAsSpec,
  });
  return {
    ...item,
    unit: spec?.unit ?? item.unit,
    spec_lsl: spec?.lsl ?? null,
    spec_usl: spec?.usl ?? null,
    judgement: result.judgement,
    judgement_reason: result.reason,
    deviation: result.deviation,
  };
}
