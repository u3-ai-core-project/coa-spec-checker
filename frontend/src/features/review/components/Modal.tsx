import { useEffect, type ReactNode } from 'react';
import '../shell/fonts';

interface ModalProps {
  /** 상자 너비(px). 시안의 다이얼로그는 500 또는 560이고, 버전 비교처럼 여러 열을 나란히 놓는 것은 760입니다. */
  width: 500 | 560 | 760;
  /** 상자 안쪽 세로 간격 */
  gap?: 'gap-3.5' | 'gap-4';
  labelledBy?: string;
  onClose(): void;
  children: ReactNode;
}

/** 검수 다이얼로그 공통 틀. 어두운 배경 위에 가운데 정렬하고 Esc로 닫습니다. */
export function Modal({ width, gap = 'gap-3.5', labelledBy, onClose, children }: ModalProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-overlay coa-font fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={`modal-box relative z-[60] flex flex-col ${gap} rounded-2xl bg-white p-6 shadow-xl`}
        style={{ width }}
      >
        {children}
      </div>
    </div>
  );
}
