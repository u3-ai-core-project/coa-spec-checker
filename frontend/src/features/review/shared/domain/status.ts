import type { DocumentStatus } from '../api/types';

/** 화면에 보이는 문서 상태 6종. extracted와 in_review는 "검수 중"으로 묶습니다. */
export type StatusKey = 'queued' | 'processing' | 'reviewing' | 'on_hold' | 'done' | 'failed';

export interface StatusMeta {
  label: string;
  color: string;
  bg: string;
  /** Icon 컴포넌트의 이름 */
  icon: 'clock' | 'spinner' | 'pencil' | 'check' | 'warn';
}

export const STATUS_META: Record<StatusKey, StatusMeta> = {
  queued: { label: '대기', color: '#5B616A', bg: '#EEF0F3', icon: 'clock' },
  processing: { label: '처리 중', color: '#2B4FCB', bg: '#EAEFFC', icon: 'spinner' },
  reviewing: { label: '검수 중', color: '#0F6A7B', bg: '#E1F3F6', icon: 'pencil' },
  on_hold: { label: '보류', color: '#9A5B00', bg: '#FBF0DF', icon: 'clock' },
  done: { label: '완료', color: '#1F2328', bg: '#E3E5E8', icon: 'check' },
  failed: { label: '오류', color: '#C0342E', bg: '#FBEAE9', icon: 'warn' },
};

/** 상태 필터 탭의 표시 순서 (전체 제외) */
export const STATUS_ORDER: StatusKey[] = ['queued', 'processing', 'reviewing', 'on_hold', 'done', 'failed'];

export function statusKey(status: DocumentStatus): StatusKey {
  switch (status) {
    case 'queued':
      return 'queued';
    case 'processing':
      return 'processing';
    case 'extracted':
    case 'in_review':
      return 'reviewing';
    case 'on_hold':
      return 'on_hold';
    case 'approved':
      return 'done';
    case 'failed':
      return 'failed';
  }
}

/** 값 수정, 확인, 처분이 가능한 상태. 승인(처분)된 문서와 추출 전 문서는 제외합니다. */
export function isEditableStatus(status: DocumentStatus): boolean {
  return status === 'extracted' || status === 'in_review' || status === 'on_hold';
}
