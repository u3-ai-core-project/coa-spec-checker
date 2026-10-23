import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './authContext'

export default function RequireAuth() {
    const { user, loading } = useAuth()
    if (loading) return <div className="p-6 text-sm text-ink-sub">불러오는 중...</div>
    if (!user) return <Navigate to="/login" replace />
    return <Outlet />
}