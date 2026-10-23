import { TOKEN_STORAGE_KEY } from '../config';

type Listener = () => void;

let unauthorizedListener: Listener | null = null;

function storage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

let memoryToken: string | null = null;

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_STORAGE_KEY) ?? memoryToken;
}

export function setToken(token: string): void {
  memoryToken = token;
  storage()?.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  memoryToken = null;
  storage()?.removeItem(TOKEN_STORAGE_KEY);
}

/** 401을 받으면 토큰을 지우고 이 리스너를 호출합니다. AuthProvider가 로그인 화면 이동을 등록합니다. */
export function onUnauthorized(listener: Listener | null): void {
  unauthorizedListener = listener;
}

export function handleUnauthorized(): void {
  clearToken();
  unauthorizedListener?.();
}
