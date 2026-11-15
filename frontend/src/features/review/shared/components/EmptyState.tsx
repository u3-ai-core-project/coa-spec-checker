import type { ReactNode } from 'react';
import { Icon } from './Icon';

interface EmptyStateProps {
  title: string;
  message: string;
  action?: ReactNode;
  note?: string;
}

/** 시안 2-0의 빈 상태. 문서가 하나도 없을 때 씁니다. */
export function EmptyState({ title, message, action, note }: EmptyStateProps) {
  return (
    <div className="empty-state flex flex-col items-center gap-3 text-center">
      <div className="empty-icon flex h-20 w-20 items-center justify-center rounded-full bg-[#EAEFFC] text-[#2B4FCB]">
        <Icon name="file" size={36} />
      </div>
      <h3 className="empty-title mt-2 text-[18px] font-bold">{title}</h3>
      <p className="empty-message text-[14px] text-[#5B616A]">{message}</p>
      {action}
      {note && <p className="empty-formats text-[12px] text-[#8A9099]">{note}</p>}
    </div>
  );
}

/** 불러오기 실패 안내 */
export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <p className="text-[14px] text-[#C0342E]">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="h-9 rounded-lg border border-[#D0D4DA] bg-white px-4 text-[13px] font-semibold"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}
