/** 문서 삭제 사유의 길이 범위(백엔드 #65 deletion_service.clean_reason): 앞뒤 공백을 뺀 2~500자. 아니면 400 REASON_REQUIRED */
export const DELETE_REASON_MIN_LENGTH = 2;
export const DELETE_REASON_MAX_LENGTH = 500;

/** 앞뒤 공백을 뺀 삭제 사유와 그 글자 수(서버처럼 글자 단위로 셉니다). */
export function cleanDeleteReason(text: string): { reason: string; length: number } {
  const reason = text.trim();
  return { reason, length: [...reason].length };
}

/** 사유가 서버 조건(2~500자)에 맞는지. 최종 판단은 서버가 합니다. */
export function isDeleteReasonValid(length: number): boolean {
  return length >= DELETE_REASON_MIN_LENGTH && length <= DELETE_REASON_MAX_LENGTH;
}
