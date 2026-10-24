// [개발 확인용 임시 코드] 개발 화면 전용 주소 옵션을 읽습니다. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.

/**
 * 개발용 옵션 값. 주소가 http://localhost:5173/dev.html?as=admin#/inspection 처럼 ? 뒤에 있어도,
 * http://localhost:5173/dev.html#/inspection?as=admin 처럼 # 뒤에 있어도 읽습니다.
 */
export function devParam(name: string): string | null {
  const fromSearch = new URLSearchParams(window.location.search).get(name);
  if (fromSearch !== null) return fromSearch;
  const hash = window.location.hash;
  const at = hash.indexOf('?');
  return at === -1 ? null : new URLSearchParams(hash.slice(at + 1)).get(name);
}
