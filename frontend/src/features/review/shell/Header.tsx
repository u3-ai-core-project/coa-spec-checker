import type { ReactNode } from 'react';
import type { Role } from '../shared/api/types';
import { RoleBadge } from '../shared/components/badges';
import './fonts';

interface HeaderProps {
  title: string;
  subtitle?: string;
  breadcrumb?: string;
  role: Role;
  /** 역할 배지 오른쪽에 둘 요소 */
  actions?: ReactNode;
}

/** 시안 상단 헤더(높이 72). 목록과 규격 관리처럼 단순한 화면용이고, 제목, 부제목, 역할은 props로 받습니다. */
export function Header({ title, subtitle, breadcrumb, role, actions }: HeaderProps) {
  return (
    <header className="header flex h-[72px] shrink-0 items-center justify-between border-b border-[#E3E5E8] bg-white px-6">
      <div className="header-title flex flex-col gap-0.5">
        {breadcrumb && <span className="header-breadcrumb text-[11px] text-[#8A9099]">{breadcrumb}</span>}
        <span className="header-docname text-[16px] font-bold">{title}</span>
        {subtitle && <span className="header-sub text-[12px] text-[#5B616A]">{subtitle}</span>}
      </div>
      <div className="header-right flex items-center gap-4">
        <RoleBadge role={role} />
        {actions}
      </div>
    </header>
  );
}
