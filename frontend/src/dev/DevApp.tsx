// [개발 확인용 임시 코드] 검수·규격 관리 화면을 띄워 보기 위한 호스트 앱입니다. 실제 앱의 라우터와 레이아웃은
// 다른 파트의 몫이고, 이 폴더(src/dev)는 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다. 주소는 해시 라우터라 dev.html#/inspection 형태입니다.
// 사이드바와 헤더는 공통 레이아웃(src/components/layout/AppLayout)을 그대로 씁니다.
import { HashRouter, Navigate, type RouteObject, useRoutes } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import { reviewRoutes } from '../features/review/routes';
import { REVIEW_PATH } from '../features/review/shared/domain/constants';
import { specsRoutes } from '../features/specs/routes';
import { AuthProvider } from './AuthProvider';
import { LoginPage } from './LoginPage';
import { PlaceholderPage } from './PlaceholderPage';
import { RequireAuth } from './RouteGuard';

const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <Navigate to={REVIEW_PATH} replace /> },
          // 다른 파트의 화면
          { path: '/upload', element: <PlaceholderPage title="업로드" /> },
          { path: '/dashboard', element: <PlaceholderPage title="대시보드" /> },
          { path: '/reports', element: <PlaceholderPage title="리포트" /> },
          // 내 파트: 검수(2번대), 규격 관리(5번대)
          ...reviewRoutes,
          ...specsRoutes,
          { path: '*', element: <Navigate to={REVIEW_PATH} replace /> },
        ],
      },
    ],
  },
];

function DevRoutes() {
  return useRoutes(routes);
}

export function DevApp() {
  return (
    <HashRouter>
      <AuthProvider>
        <DevRoutes />
      </AuthProvider>
    </HashRouter>
  );
}
