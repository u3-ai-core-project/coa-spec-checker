import type { Role } from '../types/auth'

const LABEL: Record<Role, string> = { USER: '사용자', ADMIN: '관리자' }

export default function RoleBadge({ role }: { role: Role }) {
    return (
        <span className='inline-flex items-center gap-1.5 rounded-full border border--[#e6ecfb] bg-brand-soft px-2.5 py-0.5 text-xs font-bold text-brand'>
            <span className='h-1.5 w-1.5 rounded-full bg-brand' />
            {LABEL[role]}
        </span>
    )
}