const KEY = 'coa_last_review_document';

/** 마지막으로 연 검수 문서 id. 목록에서 그 행을 강조하는 데 씁니다(저장소를 못 쓰면 null). */
export function readLastViewed(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function writeLastViewed(documentId: string): void {
  try {
    sessionStorage.setItem(KEY, documentId);
  } catch {
    // 저장소를 쓸 수 없으면 강조만 생략합니다.
  }
}
