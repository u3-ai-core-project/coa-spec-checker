import { NavLink } from 'react-router-dom';
import type { Role } from '../shared/api/types';
import { RoleBadge } from '../shared/components/badges';
import { Icon } from '../shared/components/Icon';
import './fonts';

export interface SidebarMenu {
  label: string;
  to: string;
}

// 시안(2-x, 5-x)의 메뉴 순서. 업로드, 대시보드, 리포트는 다른 파트의 화면이라 경로만 연결합니다.
const DEFAULT_MENUS: SidebarMenu[] = [
  { label: '업로드', to: '/upload' },
  { label: '검수', to: '/review' },
  { label: '대시보드', to: '/dashboard' },
  { label: '리포트', to: '/reports' },
  { label: '규격 관리', to: '/specs' },
];

interface SidebarProps {
  userName: string;
  role: Role;
  onLogout?(): void;
  menus?: SidebarMenu[];
}

/** 시안 왼쪽 사이드바(너비 240). 사용자 이름과 역할은 props로 받습니다. */
export function Sidebar({ userName, role, onLogout, menus = DEFAULT_MENUS }: SidebarProps) {
  return (
    <aside className="sidebar flex h-full w-[240px] shrink-0 flex-col border-r border-[#E3E5E8] bg-white">
      <div className="sidebar-logo flex h-[72px] items-center px-6 text-[16px] font-bold text-[#2B4FCB]">
        CoA Inspector
      </div>
      <nav className="sidebar-menu flex flex-col gap-1 px-3 pt-2">
        {menus.map((menu) => (
          <NavLink
            key={menu.to}
            to={menu.to}
            className={({ isActive }) =>
              `menu-item flex h-10 items-center rounded-lg px-3 text-[14px] ${
                isActive ? 'menu-item-active bg-[#EAEFFC] font-semibold text-[#2B4FCB]' : 'text-[#5B616A]'
              }`
            }
          >
            {menu.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-user mx-5 mb-6 mt-auto flex flex-col gap-3 border-t border-[#E3E5E8] pt-4">
        <div className="sidebar-user-info flex items-center gap-2">
          <span className="sidebar-avatar flex h-7 w-7 items-center justify-center rounded-full bg-[#D0D4DA] text-white">
            <Icon name="user" size={16} />
          </span>
          <span className="sidebar-user-name text-[14px] font-semibold">{userName}</span>
          <RoleBadge role={role} />
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="btn-logout flex h-8 w-[84px] items-center justify-center gap-1.5 rounded-lg border border-[#E3E5E8] bg-white text-[12px] text-[#5B616A]"
        >
          <Icon name="logout" size={13} />
          로그아웃
        </button>
      </div>
    </aside>
  );
}
