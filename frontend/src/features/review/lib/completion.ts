import type { ExtractionItem, LotRecommendation } from '../shared/api/types';
import { formatNumber } from '../shared/domain/format';
import { displayUnit, formatConverted } from '../shared/domain/items';
import type { Disposition } from '../shared/domain/recommendation';

/**
 * 검수 완료 다이얼로그의 화면 규칙입니다. 서버가 거절하는 조건(명세 4.12)을 미리 막아 주기 위한 것이고,
 * 실제 판단은 서버 응답(422, 400)을 따릅니다. 백엔드 확정 답변:
 *   - 처분 차단은 confidence < 0.8 이면서 reviewed=false 인 항목이 있을 때만이고, 남은 건수는 그 항목 수입니다
 *     (판정 불가, 누락, 검출한계 미기재로 인한 확인 필요는 막지 않습니다).
 *   - 로트 권고가 보류면 어떤 처분이든 사유가 필수이고, 부적합이 있으면 승인은 비활성화합니다.
 */

/** 불합격 권고(부적합 항목 있음)인 로트는 "승인"을 선택할 수 없습니다. (서버: 422 INVALID_DECISION) */
export function isDispositionLocked(disposition: Disposition, recommendation: LotRecommendation): boolean {
  return disposition === 'accept' && recommendation === 'reject';
}

/**
 * 사유가 필수인 처분인지.
 * 서버 규칙: 조건부 승인이거나 AI 권고와 다른 처분이면 필수(400 REASON_REQUIRED), 보류도 사유가 필수입니다.
 * 화면 정책: 불합격도 사유를 필수로 받습니다.
 */
export function isReasonRequired(disposition: Disposition, recommendation: LotRecommendation): boolean {
  if (disposition === 'hold' || disposition === 'conditional_accept' || disposition === 'reject') return true;
  return recommendation !== 'approve'; // 승인은 승인 권고일 때만 사유 없이 가능합니다.
}

/** "보류" 뒤에는 "로", 받침이 있는 말 뒤에는 "으로"를 붙입니다. (ㄹ 받침은 "로") */
export function withEuro(text: string): string {
  const code = text.charCodeAt(text.length - 1);
  const isHangul = code >= 0xac00 && code <= 0xd7a3;
  if (!isHangul) return `${text}으로`;
  const final = (code - 0xac00) % 28;
  return final === 0 || final === 8 ? `${text}로` : `${text}으로`;
}

/** 불합격 사유 제안. 사내 상한을 넘은 부적합 항목이 있으면 그 내용을 문장으로 만들어 줍니다. */
export function suggestRejectReason(items: ExtractionItem[]): string {
  const failed = items.find((item) => item.judgement === 'fail' && item.spec_usl !== null && item.deviation !== null);
  if (!failed || failed.spec_usl === null) return '';
  const shownUnit = displayUnit(failed);
  const unit = shownUnit ? ` ${shownUnit}` : '';
  return `${failed.normalized_name} ${formatConverted(failed)}이 사내 상한 ${formatNumber(failed.spec_usl)}${unit}을 초과하여 불합격으로 처분합니다.`;
}
