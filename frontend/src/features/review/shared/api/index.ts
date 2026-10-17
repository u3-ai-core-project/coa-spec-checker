import { USE_MOCK } from '../config';
import type { Api } from './Api';
import { HttpApi } from './http';
import { MockApi } from './mock/MockApi';

/**
 * 목업 API 인스턴스. VITE_USE_MOCK=false이면 null입니다.
 * 개발용 화면(src/dev)이 시안 비교용 시작 상태(빈 목록, 이상 패턴 등)로 바꿀 때 resetState를 부릅니다.
 */
export const mockApi: MockApi | null = USE_MOCK ? new MockApi() : null;

/** 화면이 쓰는 API 인스턴스. VITE_USE_MOCK=false이면 실제 백엔드(HttpApi), 그 외에는 목업(MockApi)을 씁니다. */
export const api: Api = mockApi ?? new HttpApi();

export type { Api } from './Api';
