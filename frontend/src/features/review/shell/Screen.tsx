import type { ReactNode } from 'react';
import './fonts';

/**
 * 화면 하나의 맨 바깥 상자. 글꼴(Pretendard)과 기본 글자색을 여기서 정하고, 헤더와 main을 세로로 쌓는 구조는 그대로 둡니다.
 * 호스트 앱이 어떤 레이아웃으로 감싸더라도 이 파트 화면의 글꼴이 같게 나오도록 라우트에서 감쌉니다.
 */
export function Screen({ children }: { children: ReactNode }) {
  return <div className="screen coa-font flex min-h-0 flex-1 flex-col text-[#1F2328]">{children}</div>;
}
