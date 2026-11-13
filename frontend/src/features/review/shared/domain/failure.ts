import type { DocumentStatus, ErrorKind, FailedStage } from '../api/types';

/** 실패한 단계의 화면 이름(백엔드 failed_stage) */
export const FAILED_STAGE_LABEL: Record<FailedStage, string> = {
  extract: '추출 실패',
  judge: '판정 실패',
  timeout: '처리 시간 초과',
  interrupted: '서버 재시작으로 중단',
};

/** 실패 종류별 안내(백엔드 error_kind) */
export const ERROR_KIND_GUIDE: Record<ErrorKind, string> = {
  transient: '일시 오류 · 다시 처리해 주세요',
  permanent: '파일을 확인해 교체 후 다시 업로드해 주세요',
};

interface FailureFields {
  status: DocumentStatus;
  failed_stage?: FailedStage | null;
  error_kind?: ErrorKind | null;
}

/**
 * 실패 문서의 단계와 종류 안내. 서버가 두 필드를 보내지 않았거나 문서가 실패 상태가 아니면 null입니다(예전 화면 그대로).
 * 알 수 없는 값(서버가 새 값을 더한 경우)은 안내를 만들지 않고 그대로 둡니다.
 */
export function failureInfo(doc: FailureFields): { stage: string | null; guide: string | null } | null {
  if (doc.status !== 'failed') return null;
  const stage = doc.failed_stage ? (FAILED_STAGE_LABEL[doc.failed_stage] ?? null) : null;
  const guide = doc.error_kind ? (ERROR_KIND_GUIDE[doc.error_kind] ?? null) : null;
  return stage || guide ? { stage, guide } : null;
}
