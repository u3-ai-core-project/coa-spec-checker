import { useState } from 'react';
import type { InquiryDraft } from '../shared/api/types';
import { Icon } from '../shared/components/Icon';

const SOURCE_LABEL: Record<InquiryDraft['source'], string> = {
  template: '템플릿',
  ai: 'AI 초안',
  template_fallback: '템플릿(AI 실패로 대체)',
};

/** "AI로 다듬기" 버튼과 그 진행 상태 */
export interface DraftAiAction {
  loading: boolean;
  error: string | null;
  /** 이미 AI 초안을 받았으면 true(버튼이 "다시 다듬기"가 됩니다) */
  hasResult: boolean;
  onRequest(): void;
}

type CopyState = 'idle' | 'copied' | 'failed';

/** 문의 초안 한 통: 제목, 본문, 복사 버튼, 생성 방식(GET /documents/{id}/follow-ups의 draft, combined_draft) */
export function DraftBox({ title, draft, ai }: { title: string; draft: InquiryDraft; ai?: DraftAiAction }) {
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
        <span className="flex items-center gap-1.5">
          {ai && (
            <button
              type="button"
              disabled={ai.loading}
              aria-busy={ai.loading}
              onClick={ai.onRequest}
              className="btn-ai-draft inline-flex h-7 items-center gap-1 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328] disabled:cursor-not-allowed disabled:text-[#8A9099]"
            >
              <Icon name={ai.loading ? 'spinner' : 'spark'} size={13} className={ai.loading ? 'animate-spin' : undefined} />
              {ai.hasResult ? 'AI로 다시 다듬기' : 'AI로 다듬기'}
            </button>
          )}
          <button
            type="button"
            onClick={() => void copyDraft()}
            className="btn-copy-draft inline-flex h-7 items-center gap-1 rounded-md border border-[#D0D4DA] bg-white px-2.5 text-[12px] font-semibold text-[#1F2328]"
          >
            <Icon name="copy" size={13} />
            {copy === 'copied' ? '복사됨' : '복사'}
          </button>
        </span>
      </div>
      {ai?.loading && (
        <span role="status" className="draft-ai-loading text-[11px] text-[#2B4FCB]">
          AI가 문의 초안을 다듬는 중입니다 (최대 3분)
        </span>
      )}
      {ai?.error && (
        <span role="alert" className="draft-ai-error text-[11px] text-[#C0342E]">
          {ai.error}
        </span>
      )}
      {draft.source === 'template_fallback' && (
        <span className="draft-fallback-notice text-[11px] text-[#8A5A00]">AI를 쓸 수 없어 기본 초안을 표시합니다</span>
      )}
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
