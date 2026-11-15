import type { ReactNode } from 'react';
import './fonts';

/**
 * 화면 하나의 맨 바깥 상자. 공통 레이아웃(AppLayout)의 본문 영역을 가득 채우고, 안내 블록과 main을 세로로 쌓습니다.
 * 글꼴(Pretendard)과 기본 글자색은 여기서 정해서, 호스트 앱이 어떤 레이아웃으로 감싸더라도 이 파트 화면의 글꼴이 같게 나옵니다.
 * 본문 바깥 여백(p-6)은 공통 레이아웃의 main이 가지므로 이 파트 화면은 따로 두지 않습니다.
 */
export function Screen({ children }: { children: ReactNode }) {
  return <div className="screen coa-font flex h-full min-h-0 flex-col gap-4 text-[#1F2328]">{children}</div>;
}
