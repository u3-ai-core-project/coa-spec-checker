import type { ApprovalLog, ExtractionItem, ReviewLog } from '../shared/api/types';
import { formatShortDateTime } from '../shared/domain/format';
import { withUnit } from '../shared/domain/items';
import { DISPOSITION_META, followUpLabel } from '../shared/domain/recommendation';

export type HistoryKind = '검수 완료' | '보류' | '승인 취소' | '값 수정' | '값 확인' | '매핑 수정';

const KIND_COLOR: Record<HistoryKind, string> = {
  '검수 완료': '#2B4FCB',
  보류: '#5B616A',
  '승인 취소': '#C0342E',
  '값 수정': '#2B4FCB',
  '값 확인': '#2B4FCB',
  '매핑 수정': '#2B4FCB',
};

export interface HistoryEntry {
  key: string;
  /** ISO 일시 */
  at: string;
  /** 10-05 15:02 형식 */
  when: string;
  kind: HistoryKind;
  color: string;
  who: string;
  detail: string;
}

function withReason(parts: string[], reason: string | null | undefined): string {
  return reason ? [...parts, `사유: ${reason}`].join(' · ') : parts.join(' · ');
}

/**
 * 승인 이력 카드에 보여 줄 항목을 만듭니다. 처분·보류·승인 취소(approval-logs)와 값 수정·확인(review-logs)을
 * 시간 역순으로 합칩니다. 보류와 승인 취소는 서로 다른 이력이라 action(approve, hold, cancel)으로 구분해 표시합니다.
 * TODO(백엔드 협의): 시안 2-5의 "검수 완료 → 승인" 2단계는 API가 /approve 한 번이므로 처분(승인) 이력 한 줄로 보여 줍니다.
 */
export function buildHistory(input: {
  reviewLogs: ReviewLog[];
  approvalLogs: ApprovalLog[];
  items: Pick<ExtractionItem, 'item_id' | 'normalized_name' | 'unit'>[];
}): HistoryEntry[] {
  const byId = new Map(input.items.map((item) => [item.item_id, item]));
  const entries: HistoryEntry[] = [];

  input.approvalLogs.forEach((log, index) => {
    let kind: HistoryKind;
    let detail: string;
    if (log.action === 'approve') {
      kind = '검수 완료';
      const decision = log.decision ? DISPOSITION_META[log.decision].label : '-';
      detail = withReason([`처분: ${decision}`], log.reason);
    } else if (log.action === 'hold') {
      kind = '보류';
      detail = withReason([`후속 조치: ${followUpLabel(log.follow_up)}`], log.reason);
    } else {
      kind = '승인 취소';
      detail = withReason([], log.reason);
    }
    entries.push({
      key: `approval-${index}`,
      at: log.created_at,
      when: formatShortDateTime(log.created_at),
      kind,
      color: KIND_COLOR[kind],
      who: log.user_name,
      detail,
    });
  });

  input.reviewLogs.forEach((log, index) => {
    const item = byId.get(log.item_id);
    const name = item?.normalized_name ?? log.item_id;
    const unit = item?.unit ?? null;
    let kind: HistoryKind;
    let detail: string;
    if (log.action === 'edit') {
      kind = '값 수정';
      detail = withReason([`${name} ${log.before_value} → ${withUnit(log.after_value, unit)}`], log.reason);
    } else if (log.action === 'confirm') {
      kind = '값 확인';
      detail = `${name} ${withUnit(log.after_value, unit)} 확인됨`;
    } else {
      kind = '매핑 수정';
      detail = `${log.before_value} → ${log.after_value}`;
    }
    entries.push({
      key: `review-${index}`,
      at: log.reviewed_at,
      when: formatShortDateTime(log.reviewed_at),
      kind,
      color: KIND_COLOR[kind],
      who: log.reviewer_name,
      detail,
    });
  });

  // 최근 이력이 위에 오도록 시간 역순. 같은 시각이면 나중에 쌓인 것을 위에 둡니다.
  return entries
    .map((entry, order) => ({ entry, order }))
    .sort((a, b) => new Date(b.entry.at).getTime() - new Date(a.entry.at).getTime() || b.order - a.order)
    .map(({ entry }) => entry);
}
