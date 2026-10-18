import { NavLink } from 'react-router-dom'
import { NAV_ITEMS } from '../../navigation'
import { CURRENT_USER } from '../../currentUser'
import RoleBadge from '../RoleBadge'
import { LogoutIcon, UserIcon } from '../icons'

export default function Sidebar() {
    return (
        <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-white">
            <div className="px-6 pt-6 pb-5 text-base font-bold text-brand">
                CoA Inspector
            </div>

            <nav className="flex flex-col gap-1 px-3">
                {NAV_ITEMS.map((item) => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        className={({ isActive }) =>
                            `rounded-lg px-3 py-2.5 text-sm ${isActive
                                ? 'bg-brand-soft font-bold text-brand'
                                : 'text-ink-sub hover:bg-surface'
                            }`
                        }
                    >
                        {item.label}
                    </NavLink>
                ))}
            </nav>

            <div className="mt-auto border-t border-line p-4">
                <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-300">
                        <UserIcon />
                    </div>
                    <span className="text-sm font-bold">{CURRENT_USER.name}</span>
                    <RoleBadge role={CURRENT_USER.role} />
                </div>
                <button
                    type="button"
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs text-ink-sub hover:bg-surface"
                >
                    <LogoutIcon />
                    로그아웃
                </button>
            </div>
        </aside>
    )
}