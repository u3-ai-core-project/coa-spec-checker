import { createContext, useContext } from 'react';
import type { Role } from './api/types';

/**
 * 검수·규격 관리 화면이 필요로 하는 로그인 사용자 정보입니다.
 * 로그인과 인증은 다른 파트의 몫이라, 호스트 앱이 로그인한 사용자를 CurrentUserProvider로 넘겨 줍니다.
 * (개발 확인용 호스트는 src/dev/AuthContext.tsx입니다.)
 */
export interface CurrentUser {
  id: number;
  name: string;
  role: Role;
}

const CurrentUserContext = createContext<CurrentUser | null>(null);

export const CurrentUserProvider = CurrentUserContext.Provider;

/** 로그인한 사용자. CurrentUserProvider 안쪽 화면에서만 씁니다. */
export function useCurrentUser(): CurrentUser {
  const user = useContext(CurrentUserContext);
  if (!user) throw new Error('CurrentUserProvider 안에서만 쓸 수 있습니다.');
  return user;
}
