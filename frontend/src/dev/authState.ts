// [개발 확인용 임시 코드] 로그인과 인증은 다른 파트의 몫입니다. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { createContext, useContext } from 'react';
import type { AuthUser, Role } from '../features/review/shared/api/types';

export interface AuthState {
  user: AuthUser | null;
  /** 저장된 토큰으로 /auth/me를 확인하는 중 */
  loading: boolean;
  login(username: string, password: string): Promise<void>;
  logout(): void;
  hasRole(role: Role): boolean;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth는 AuthProvider 안에서만 쓸 수 있습니다.');
  return value;
}
