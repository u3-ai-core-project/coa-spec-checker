// [개발 확인용 진입점] dev.html이 불러옵니다. 실제 앱의 진입점(src/main.tsx)은 건드리지 않고, 공용 스타일만 가져다 씁니다.
import '../index.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { DevApp } from './DevApp';
import { autoLoginFromQuery } from './autoLogin';
import { applyMockScenario } from './scenarios';

applyMockScenario();

// 개발용 자동 로그인(?as=user|admin)이 끝난 뒤에 화면을 그립니다. 그 외에는 바로 시작합니다.
autoLoginFromQuery()
  .catch(() => undefined)
  .finally(() => {
    // 공통 레이아웃(사이드바, 헤더)에도 이 파트의 글꼴(Pretendard)이 보이게 합니다. 실제 앱에서는 전역 글꼴 설정이 필요합니다.
    document.getElementById('root')!.classList.add('coa-font');
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <DevApp />
      </StrictMode>,
    );
  });
