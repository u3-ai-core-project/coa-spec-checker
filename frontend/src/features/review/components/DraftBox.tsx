import { useState } from 'react';
import type { InquiryDraft } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';

const SOURCE_LABEL: Record<InquiryDraft['source'], string> = {
  template: '템플릿',
  ai: 'AI',
  template_fallback: '템플릿(AI 실패로 대체)',
};

type CopyState = 'idle' | 'copied' | 'failed';

/** 문의 초안 한 통: 제목, 본문, 복사 버튼, 생성 방식(GET /documents/{id}/follow-ups의 draft, combined_draft) */
export function DraftBox({ title, draft }: { title: string; draft: InquiryDraft }) {
  const [copy, setCopy] = useState<CopyState>('idle');

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.body}`);
      setCopy('copied');
    } catch {
      setCopy('failed'); // 클립보드를 쓸 수 없으면 본문을 직접 선택해 복사하도록 안내합니다.
    }
  }

  return (
    <div className="exception-draft flex min-w-0 flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[#8A9099]">
          {title}
          <span className="draft-source-chip inline-flex h-5 items-center rounded bg-[#EEF0F3] px-1.5 text-[10px] font-semibold text-[#5B616A]">
            {SOURCE_LABEL[draft.source] ?? draft.source}
          </span>
        </span>
        <button
          type="button"
          onClick={() => void copyDraft()}
          className="btn-copy-draft inline-flex h-7 items-center gap-1 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328]"
        >
          <Icon name="copy" size={13} />
          {copy === 'copied' ? '복사됨' : '복사'}
        </button>
      </div>
      <span className="draft-subject truncate text-[12px] font-semibold">{draft.subject}</span>
      <textarea
        readOnly
        value={draft.body}
        aria-label={`${title} 본문`}
        className="draft-body h-[156px] w-full resize-none rounded-md border border-[#D0D4DA] bg-white px-2.5 py-2 text-[12px] leading-snug"
      />
      {copy === 'failed' && <span className="text-[11px] text-[#C0342E]">복사하지 못했습니다. 본문을 직접 선택해 복사해 주십시오.</span>}
    </div>
  );
}
