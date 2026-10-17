import type { RouteObject } from 'react-router-dom';
import { Screen } from '../review/shell/Screen';
import { RequireAdmin } from './components/RequireAdmin';
import { MappingDictPage } from './MappingDictPage';
import { SpecEditPage } from './SpecEditPage';
import { SpecsPage } from './SpecsPage';

/**
 * 규격 관리(5번대) 화면의 라우트. 호스트 앱이 로그인한 사용자 안쪽(CurrentUserProvider 아래)에 이어 붙입니다.
 * 규격 수정과 매핑 사전은 관리자만 들어갈 수 있습니다. 각 화면은 Screen으로 감싸 글꼴을 이 파트에서 정합니다.
 */
export const specsRoutes: RouteObject[] = [
  {
    path: '/specs',
    element: (
      <Screen>
        <SpecsPage />
      </Screen>
    ),
  },
  {
    element: <RequireAdmin />,
    children: [
      {
        path: '/specs/edit',
        element: (
          <Screen>
            <SpecEditPage />
          </Screen>
        ),
      },
      {
        path: '/specs/mappings',
        element: (
          <Screen>
            <MappingDictPage />
          </Screen>
        ),
      },
    ],
  },
];
