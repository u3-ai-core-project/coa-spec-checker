/** API 에러 응답({ success: false, error: { code, message } })을 담는 예외입니다. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** 에러 코드별 화면 안내 문구입니다. 서버 message는 사용하지 않고 화면 문구로 통일합니다. */
const MESSAGES: Record<string, string> = {
  UNKNOWN_ITEM_NAME: '사내 규격에 없는 항목명입니다.',
  UNKNOWN_SPEC_SET: '등록되지 않은 규격 세트입니다.',
  VALIDATION_ERROR: '입력한 값의 형식이 올바르지 않습니다.',
  REASON_REQUIRED: '사유를 입력해 주십시오.',
  INVALID_SPEC_RANGE: '규격 하한은 상한보다 클 수 없습니다.',
  INVALID_CREDENTIALS: '아이디 또는 비밀번호가 올바르지 않습니다.',
  UNAUTHORIZED: '로그인이 만료되었습니다. 다시 로그인해 주십시오.',
  FORBIDDEN: '이 기능을 사용할 권한이 없습니다.',
  DOCUMENT_NOT_FOUND: '존재하지 않는 문서입니다.',
  ITEM_NOT_FOUND: '문서에 존재하지 않는 항목입니다.',
  SPEC_NOT_FOUND: '존재하지 않는 규격 항목입니다.',
  NOT_FOUND: '요청한 대상을 찾을 수 없습니다.',
  ALREADY_APPROVED: '이미 처분된 문서입니다.',
  NOT_APPROVED: '처분되지 않은 문서입니다.',
  NOT_READY: '아직 추출이 끝나지 않은 문서입니다.',
  REISSUE_UNRESOLVED: '같은 로트의 CoA가 여러 개입니다. 기준 버전을 먼저 선택해야 처분할 수 있습니다.',
  NOT_BASE_VERSION: '기준 버전으로 선택된 문서가 아니라 처분할 수 없습니다.',
  NOTHING_TO_REVERT: '되돌릴 변경 이력이 없습니다.',
  DB_UNAVAILABLE: '서버의 데이터베이스에 연결하지 못했습니다. 잠시 후 다시 시도해 주십시오.',
  PENDING_LOW_CONFIDENCE_ITEMS: '신뢰도 낮음 항목을 모두 수정하거나 확인한 뒤에 검수를 완료할 수 있습니다.',
  INVALID_DECISION: '부적합 항목이 있는 로트는 승인할 수 없습니다.',
  TIMEOUT: '서버 응답이 너무 오래 걸려 요청을 중단했습니다. 잠시 후 다시 시도해 주십시오.',
};

export const FALLBACK_ERROR_MESSAGE = '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주십시오.';

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? FALLBACK_ERROR_MESSAGE;
  }
  return FALLBACK_ERROR_MESSAGE;
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code);
}
