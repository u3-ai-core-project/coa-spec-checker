import type { Judgement, JudgementSummary, LotRecommendation, ReviewedItem } from '../shared/api/types';

/**
 * 회신값을 넣고 서버가 다시 판정한 결과(시안 2-12b). PATCH 응답의 item, lot_recommendation, summary를 입력 전 값과 함께 둡니다.
 * 판정과 건수는 화면에서 계산하지 않고 서버 응답을 그대로 씁니다.
 */
export interface ReplyResult {
  itemId: string;
  name: string;
  beforeJudgement: Judgement;
  after: ReviewedItem;
  beforeRecommendation: LotRecommendation;
  afterRecommendation: LotRecommendation;
  beforeSummary: JudgementSummary;
  afterSummary: JudgementSummary;
}

/** 해결 조건을 만족해 판정이 적합이 되고 예외(사유 코드)가 사라진 경우 */
export function isResolved(result: ReplyResult): boolean {
  return result.after.judgement === 'pass' && !result.after.reason_code;
}
