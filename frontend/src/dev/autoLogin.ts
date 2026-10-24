// [개발 확인용 임시 코드] 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { api } from '../features/review/shared/api';
import { setToken } from '../features/review/shared/api/session';
import { USE_MOCK } from '../features/review/shared/config';
import { devParam } from './params';

/**
 * 개발용 자동 로그인. 목업 모드의 개발 서버에서만 동작하고, 주소에 ?as=user 또는 ?as=admin을 붙이면
 * 로그인 화면을 거치지 않고 해당 목업 계정으로 들어갑니다. 시안과 화면을 나란히 비교할 때 씁니다.
 */
export async function autoLoginFromQuery(): Promise<void> {
  if (!USE_MOCK || !import.meta.env.DEV) return;
  const as = devParam('as');
  if (as !== 'user' && as !== 'admin') return;
  const result = await api.login(as, as);
  setToken(result.access_token);
}
