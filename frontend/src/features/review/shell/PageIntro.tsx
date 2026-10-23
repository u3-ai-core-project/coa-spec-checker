import type { ReactNode } from 'react';
import './fonts';

interface PageIntroProps {
  title: string;
  subtitle?: string;
  breadcrumb?: string;
  /** 오른쪽에 둘 요소 */
  actions?: ReactNode;
}

/**
 * 공통 레이아웃의 헤더는 화면 제목만 보여 주므로, 이 파트 화면의 설명(부제목, 경로)은 본문 맨 위에 이 블록으로 둡니다.
 * 시안의 헤더 안 부제목 자리를 대신하는 기본 형태입니다.
 */
export function PageIntro({ title, subtitle, breadcrumb, actions }: PageIntroProps) {
  return (
    <div className="page-intro flex shrink-0 items-end justify-between gap-4">
      <div className="flex flex-col gap-0.5">
        {breadcrumb && <span className="page-intro-breadcrumb text-[11px] text-[#8A9099]">{breadcrumb}</span>}
        <span className="page-intro-title text-[16px] font-bold">{title}</span>
        {subtitle && <span className="page-intro-sub text-[12px] text-[#5B616A]">{subtitle}</span>}
      </div>
      {actions}
    </div>
  );
}
