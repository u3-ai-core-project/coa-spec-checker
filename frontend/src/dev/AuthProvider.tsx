// [개발 확인용 임시 코드] 로그인과 인증은 다른 파트의 몫입니다. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../features/review/shared/api';
import type { AuthUser } from '../features/review/shared/api/types';
import { clearToken, getToken, onUnauthorized, setToken } from '../features/review/shared/api/session';
import { AuthContext as CommonAuthContext } from '../auth/authContext';
import { AuthContext, type AuthState } from './authState';

/** 로그인한 사용자와 역할을 전역 상태로 관리합니다. 401을 받으면 토큰을 지우고 로그인 화면으로 이동합니다. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getToken() !== null);

  useEffect(() => {
    onUnauthorized(() => {
      setUser(null);
      navigate('/login', { replace: true });
    });
    return () => onUnauthorized(null);
  }, [navigate]);

  useEffect(() => {
    if (getToken() === null) return;
    let alive = true;
    api
      .me()
      .then((me) => {
        if (!alive) return;
        setUser(me);
      })
      .catch(() => {
        // 401이면 onUnauthorized가 이미 처리합니다. 그 외 오류는 로그인 화면으로 보냅니다.
        if (alive) setUser(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.login(username, password);
    setToken(result.access_token);
    // 역할은 /auth/me의 role로 분기합니다.
    const me = await api.me();
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, login, logout, hasRole: (role) => user?.role === role }),
    [user, loading, login, logout],
  );

  // 공통 레이아웃(사이드바, 헤더)은 src/auth의 useAuth()로 사용자를 읽으므로 같은 로그인 상태를 그쪽 컨텍스트에도 넘깁니다.
  const common = useMemo(
    () => ({ user: user ? { ...user, username: user.username ?? '' } : null, loading, login, logout }),
    [user, loading, login, logout],
  );

  return (
    <AuthContext.Provider value={value}>
      <CommonAuthContext.Provider value={common}>{children}</CommonAuthContext.Provider>
    </AuthContext.Provider>
  );
}
