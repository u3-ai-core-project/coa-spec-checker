import type { DocumentDetail } from '../shared/api/types';
import { DispositionBadge } from '../shared/components/badges';
import { formatDateTime } from '../shared/domain/format';

/**
 * 처분이 끝난 문서의 처분 결과 요약 (시안 2-5).
 * API는 /approve 한 번이고 처분자와 승인자가 같으므로, 시안의 "검수 완료 → 승인" 2단계 대신 처분 한 줄만 보여 줍니다.
 * TODO(백엔드 협의): 팀에서 2단계 승인을 확정하면 승인자·승인 일시 줄을 추가합니다.
 */
export function ApprovalSummary({ doc }: { doc: DocumentDetail }) {
  if (!doc.final_decision) return null;
  return (
    <div className="approval-summary flex flex-col gap-1.5 border-b border-[#E3E5E8] bg-[#F9FAFB] px-5 py-2.5 text-[12px]">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <span className="text-[#5B616A]">처분 결과</span>
          <DispositionBadge disposition={doc.final_decision} />
        </span>
        <span className="text-[#5B616A]">
          처분자 <b className="font-semibold text-[#1F2328]">{doc.approved_by ?? '-'}</b> ·{' '}
          <span className="tabular-nums">{formatDateTime(doc.approved_at)}</span>
        </span>
      </div>
    </div>
  );
}
