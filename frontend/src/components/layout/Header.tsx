import { useLocation } from 'react-router-dom'
import { NAV_ITEMS } from '../../navigation'
import { useAuth } from '../../auth/authContext'
import RoleBadge from '../RoleBadge'

export default function Header() {
    const { pathname } = useLocation()
    const { user } = useAuth()
    if (!user) return null
    const title = NAV_ITEMS.find((item) => pathname.startsWith(item.path))?.label ?? ''

    return (
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-line bg-white px-6">
            <h1 className="text-base font-bold">{title}</h1>
            <RoleBadge role={user.role} />
        </header>
    )
}