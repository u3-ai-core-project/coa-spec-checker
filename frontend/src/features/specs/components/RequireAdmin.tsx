import { Navigate, Outlet } from 'react-router-dom';
import { useCurrentUser } from '../../review/shared/currentUser';

/**
 * 규격 수정과 매핑 사전은 관리자만 들어갈 수 있습니다. 사용자가 주소로 들어오면 규격 조회 화면으로 돌려보냅니다.
 * 권한 체크는 화면 분기와 백엔드 API 양쪽에서 이루어집니다(서버는 403 FORBIDDEN).
 */
export function RequireAdmin() {
  const user = useCurrentUser();
  if (user.role !== 'ADMIN') return <Navigate to="/specs" replace />;
  return <Outlet />;
}
