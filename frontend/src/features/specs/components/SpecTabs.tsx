import { Link } from 'react-router-dom';

/** 규격 관리 탭. 매핑 사전 탭은 관리자에게만 보입니다(호출하는 쪽에서 관리자일 때만 렌더링합니다). */
export function SpecTabs({ active }: { active: 'specs' | 'mappings' }) {
  const tab = (label: string, to: string, on: boolean) => (
    <Link
      to={to}
      className={`spec-tab flex h-9 items-center border-b-2 px-1 text-[14px] font-semibold ${
        on ? 'border-[#2B4FCB] text-[#2B4FCB]' : 'border-transparent text-[#5B616A]'
      }`}
    >
      {label}
    </Link>
  );
  return (
    <div className="spec-tabs flex gap-6 px-1">
      {tab('규격 목록', '/specs', active === 'specs')}
      {tab('매핑 사전 · 단위 환산표', '/specs/mappings', active === 'mappings')}
    </div>
  );
}
