import type { RouteObject } from 'react-router-dom';
import { ReviewListPage } from './ReviewListPage';
import { ReviewPage } from './ReviewPage';
import { REVIEW_PATH } from './shared/domain/constants';
import { Screen } from './shell/Screen';

/**
 * 검수(2번대) 화면의 라우트. 호스트 앱이 로그인한 사용자 안쪽(CurrentUserProvider 아래)에 이어 붙입니다.
 * 화면이 늘어날 때마다 이 배열에 추가합니다. 각 화면은 Screen으로 감싸 글꼴을 이 파트에서 정합니다.
 */
export const reviewRoutes: RouteObject[] = [
  {
    path: REVIEW_PATH,
    element: (
      <Screen>
        <ReviewListPage />
      </Screen>
    ),
  },
  {
    path: `${REVIEW_PATH}/:documentId`,
    element: (
      <Screen>
        <ReviewPage />
      </Screen>
    ),
  },
];
