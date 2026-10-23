import type { ReactNode } from 'react';

interface ActionBarProps {
  readonly: boolean;
  /** 수정 또는 확인하지 않은 신뢰도 낮음 항목 수(N) */
  pending: number;
  onComplete?(): void;
  /** 값 확인 등 서버 요청이 실패했을 때의 안내 */
  error?: string | null;
  /** 읽기 전용(처분 완료) 문서에 둘 버튼. 예: 관리자의 승인 취소 */
  readonlyAction?: ReactNode;
}

export const MSG_PENDING = (count: number) => `확인 필요 ${count}건을 처리해야 검수를 완료할 수 있습니다.`;
export const MSG_READY = '모든 항목이 처리되었습니다. 처분을 선택해 검수를 완료해 주십시오.';
export const MSG_READONLY = '읽기 전용입니다. 승인 취소는 관리자만 할 수 있습니다.';

/**
 * 하단 액션 바. 시안처럼 "검수 완료" 버튼은 항상 누를 수 있고, 신뢰도 낮음 항목이 남아 있으면 안내 문구로
 * 남은 건수를 알려 줍니다. 그 상태에서 누르면 검수 완료 다이얼로그가 "확인 필요 N건이 남아 있습니다"로
 * 처분을 막습니다(시안 2-2b). 서버도 같은 경우를 422(PENDING_LOW_CONFIDENCE_ITEMS)로 거절합니다.
 */
export function ActionBar({ readonly, pending, onComplete, error, readonlyAction }: ActionBarProps) {
  if (readonly) {
    return (
      <>
        <p className="action-bar-message text-[12px] leading-snug text-[#5B616A]">{MSG_READONLY}</p>
        {readonlyAction}
      </>
    );
  }
  return (
    <>
      {error ? (
        <p className="action-bar-message text-[12px] leading-snug text-[#C0342E]">{error}</p>
      ) : (
        <p className="action-bar-message text-[12px] leading-snug text-[#5B616A]">{pending > 0 ? MSG_PENDING(pending) : MSG_READY}</p>
      )}
      <button
        type="button"
        onClick={onComplete}
        className="btn-approve h-10 shrink-0 rounded-lg bg-[#2B4FCB] px-5 text-[14px] font-semibold text-white"
      >
        검수 완료
      </button>
    </>
  );
}
