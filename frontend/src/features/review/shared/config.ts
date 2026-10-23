/**
 * 백엔드 API 주소를 정리합니다. 환경변수는 VITE_API_BASE_URL(예: http://localhost:8000) 하나만 씁니다.
 * - 값 끝의 "/"를 모두 지웁니다.
 * - "/api/v1"로 끝나지 않으면 "/api/v1"을 붙입니다.
 * 이 처리는 여기서만 합니다. 다른 곳에서는 API_BASE를 그대로 가져다 씁니다.
 */
export function normalizeApiBase(value: string | undefined): string {
  const trimmed = (value ?? 'http://localhost:8000').trim().replace(/\/+$/, '');
  return trimmed.endsWith('/api/v1') ? trimmed : `${trimmed}/api/v1`;
}

export const API_BASE: string = normalizeApiBase(import.meta.env.VITE_API_BASE_URL as string | undefined);

/**
 * 'false'로 지정하지 않으면 목업 API를 씁니다. 백엔드가 준비되면 VITE_USE_MOCK=false로 전환합니다.
 * 이 변수는 이 파트(검수, 규격 관리) 안에서만 씁니다.
 */
export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK !== 'false';

export const TOKEN_STORAGE_KEY = 'coa_access_token';
