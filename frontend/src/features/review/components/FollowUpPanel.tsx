import { useState } from 'react';
import type { FollowUpLine, FollowUpsResponse, InquiryDraft } from '../shared/api/types';
import { followUpLabel } from '../shared/domain/recommendation';
import { STATUS_META, statusKey } from '../shared/domain/status';

const SOURCE_LABEL: Record<InquiryDraft['source'], string> = {
  template: '템플릿',
  ai: 'AI',
  template_fallback: '템플릿(AI 실패로 대체)',
};

function Lines({ title, lines }: { title: string; lines: FollowUpLine[] }) {
  if (lines.length === 0) return null;
  return (
    <div className="followup-lines flex flex-col gap-1">
      <span className="text-[12px] font-semibold text-[#5B616A]">{`${title} · ${lines.length}건`}</span>
      <ul className="flex flex-col gap-1.5">
        {lines.map((line) => (
          <li key={`${line.target}-${line.code}`} className="followup-line flex flex-col gap-0.5 rounded-md bg-[#F4F5F7] px-2.5 py-1.5 text-[12px] leading-snug text-[#5B616A]">
            <span>
              <b className="font-semibold text-[#1F2328]">{line.target}</b> · {line.label}
            </span>
            {line.why && <span>왜 문제인가: {line.why}</span>}
            {line.condition && <span>해결 조건: {line.condition}</span>}
            {line.raw_value && <span>CoA 기재: {line.raw_value}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DraftBox({ title, draft }: { title: string; draft: InquiryDraft }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.body}`);
      setCopied(true);
    } catch {
      setCopied(false); // 클립보드를 쓸 수 없으면 아래 본문을 직접 선택해 복사합니다.
    }
  }

  return (
    <div className="followup-draft flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-semibold text-[#5B616A]">{title}</span>
        <button
          type="button"
          onClick={() => void copy()}
          className="btn-copy-draft h-7 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold"
        >
          {copied ? '복사됨' : '복사'}
        </button>
      </div>
      <span className="text-[12px] font-semibold text-[#1F2328]">{draft.subject}</span>
      <textarea
        readOnly
        value={draft.body}
        aria-label={`${title} 본문`}
        className="followup-draft-body h-36 w-full resize-none rounded-md border border-[#D0D4DA] bg-white px-2.5 py-2 text-[12px] leading-snug"
      />
      <span className="text-[11px] text-[#8A9099]">{`생성 방식: ${SOURCE_LABEL[draft.source] ?? draft.source}`}</span>
    </div>
  );
}

/**
 * [v1.4] 후속 조치와 공급사 문의 초안(GET /documents/{id}/follow-ups). 시안에 없는 영역이라 기본 형태로 항목 목록 맨 아래에 두고,
 * 접어 둔 채 시작합니다. 공급사에 요청할 것, 내부에서 확인할 것, 이 로트의 문의 초안, 같은 공급사의 열린 요청과 묶음 초안을 보여 줍니다.
 */
export function FollowUpPanel({ followUps }: { followUps: FollowUpsResponse }) {
  const [open, setOpen] = useState(false);
  const [showCombined, setShowCombined] = useState(false);
  const total = followUps.supplier_lines.length + followUps.internal_lines.length;
  if (total === 0) return null;

  return (
    <section className="followup-panel border-t border-[#E3E5E8] px-5 py-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="followup-toggle flex w-full items-center justify-between text-left text-[12px] font-semibold text-[#8A9099]"
      >
        <span>{`후속 조치 · 문의 초안 · ${total}건`}</span>
        <span>{open ? '접기' : '펼치기'}</span>
      </button>
      {open && (
        <div className="followup-body mt-2 flex flex-col gap-3">
          {followUps.suggested_follow_up && (
            <span className="followup-suggested text-[12px] text-[#5B616A]">
              보류할 때 추천 후속 조치: <b className="font-semibold text-[#1F2328]">{followUpLabel(followUps.suggested_follow_up)}</b>
            </span>
          )}
          <Lines title="공급사에 요청" lines={followUps.supplier_lines} />
          <Lines title="내부에서 확인" lines={followUps.internal_lines} />
          {followUps.draft && <DraftBox title="문의 초안 (이 로트)" draft={followUps.draft} />}
          {followUps.open_documents.length > 1 && (
            <div className="followup-open flex flex-col gap-1">
              <span className="text-[12px] font-semibold text-[#5B616A]">{`같은 공급사의 열린 요청 · ${followUps.open_documents.length}건`}</span>
              <ul className="flex flex-col gap-0.5 text-[12px] text-[#5B616A]">
                {followUps.open_documents.map((entry) => (
                  <li key={entry.document_id}>
                    {`${entry.lot_no ?? entry.document_id} · ${STATUS_META[statusKey(entry.status)].label} · 요청 ${entry.request_count}건`}
                  </li>
                ))}
              </ul>
              {followUps.combined_draft && (
                <>
                  <button
                    type="button"
                    onClick={() => setShowCombined((value) => !value)}
                    className="btn-combined-draft h-7 self-start rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold"
                  >
                    {showCombined ? '묶음 초안 접기' : '묶음 초안 보기'}
                  </button>
                  {showCombined && <DraftBox title="묶음 문의 초안 (같은 공급사)" draft={followUps.combined_draft} />}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
