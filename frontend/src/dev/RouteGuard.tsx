// [개발 확인용 임시 코드] 라우트 가드는 다른 파트의 몫입니다. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { CurrentUserProvider } from '../features/review/shared/currentUser';
import { useAuth } from './authState';

/**
 * 로그인하지 않았으면 로그인 화면으로 보내고, 로그인했으면 검수·규격 관리 화면이 쓰는
 * CurrentUserProvider에 사용자 정보를 넘겨 줍니다.
 */
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="p-6 text-[14px] text-[#5B616A]">불러오는 중입니다.</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return (
    <CurrentUserProvider value={{ id: user.id, name: user.name, role: user.role }}>
      <Outlet />
    </CurrentUserProvider>
  );
}
