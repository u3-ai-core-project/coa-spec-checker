import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { api } from '../shared/api';
import { errorMessage } from '../shared/api/errors';
import { Icon } from '../shared/components/Icon';
import { useAsync } from '../shared/hooks/useAsync';
import type { PdfHighlight } from './PdfViewer';

// react-pdf는 크기가 커서 검수 화면을 열 때만 불러옵니다.
const PdfViewer = lazy(() => import('./PdfViewer'));

interface PdfPanelProps {
  documentId: string;
  page: number;
  onPageChange(page: number): void;
  highlights: PdfHighlight[];
  /** 문서 아래에 이어 붙일 영역(승인 이력 카드 등) */
  footer?: ReactNode;
}

function NavButton({ icon, disabled, onClick }: { icon: 'chev_l' | 'chev_r'; disabled: boolean; onClick(): void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`btn-page flex h-7 w-7 items-center justify-center rounded-md border border-[#D0D4DA] bg-white text-[#5B616A]${
        disabled ? ' opacity-40' : ''
      }`}
    >
      <Icon name={icon} size={14} />
    </button>
  );
}

/** 좌측 원본 문서 영역. 원본은 토큰이 필요하므로 fetch로 받아 Blob URL로 뷰어에 전달합니다. */
export function PdfPanel({ documentId, page, onPageChange, highlights, footer }: PdfPanelProps) {
  const [numPages, setNumPages] = useState(1);
  const file = useAsync(async () => {
    const blob = await api.getDocumentFile(documentId);
    return { url: URL.createObjectURL(blob), isImage: blob.type.startsWith('image/') };
  }, [documentId]);

  // Blob URL은 문서를 바꾸거나 화면을 떠날 때 해제합니다.
  const url = file.data?.url;
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  return (
    <section className="pdf-viewer flex min-w-0 flex-1 flex-col gap-3">
      <div className="pdf-viewer-caption flex h-7 items-center justify-between text-[12px] text-[#5B616A]">
        <span>
          원본 문서 · {`${page}/${numPages}페이지`}{' '}
          <span className="ml-2 text-[#8A9099]">항목을 선택하면 해당 페이지로 이동합니다.</span>
        </span>
        <div className="pdf-pager flex items-center gap-1.5">
          <NavButton icon="chev_l" disabled={page <= 1} onClick={() => onPageChange(page - 1)} />
          <span className="w-12 text-center font-semibold text-[#1F2328]">
            {page} / {numPages}
          </span>
          <NavButton icon="chev_r" disabled={page >= numPages} onClick={() => onPageChange(page + 1)} />
        </div>
      </div>
      <div className="pdf-document relative min-h-0 flex-1 overflow-hidden rounded-md border border-[#E3E5E8] bg-white shadow-[0_2px_4px_rgba(16,24,40,0.06),0_8px_24px_rgba(16,24,40,0.08)]">
        {file.error && !file.data ? (
          <div className="flex h-full items-center justify-center text-[13px] text-[#C0342E]">{errorMessage(file.error)}</div>
        ) : file.data ? (
          <Suspense fallback={<div className="p-6 text-[13px] text-[#8A9099]">원본을 불러오는 중입니다.</div>}>
            <PdfViewer
              fileUrl={file.data.url}
              isImage={file.data.isImage}
              page={page}
              highlights={highlights}
              onNumPages={setNumPages}
            />
          </Suspense>
        ) : (
          <div className="p-6 text-[13px] text-[#8A9099]">원본을 불러오는 중입니다.</div>
        )}
      </div>
      {footer}
    </section>
  );
}
