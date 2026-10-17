import { Outlet } from 'react-router-dom';
import type { Role } from '../shared/api/types';
import { Sidebar, type SidebarMenu } from './Sidebar';
import './fonts';

interface AppShellProps {
  userName: string;
  role: Role;
  onLogout?(): void;
  menus?: SidebarMenu[];
}

/** 사이드바와 본문 영역. 본문(Outlet)에는 각 화면이 자기 헤더와 main을 그립니다. 시안 프레임과 같은 구조입니다. */
export function AppShell({ userName, role, onLogout, menus }: AppShellProps) {
  return (
    <div className="frame coa-font flex h-screen min-w-[1280px] overflow-hidden bg-[#F4F5F7] text-[#1F2328]">
      <Sidebar userName={userName} role={role} onLogout={onLogout} menus={menus} />
      <div className="main flex h-full min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}
