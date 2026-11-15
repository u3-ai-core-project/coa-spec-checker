import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './authContext'

export default function RequireAuth() {
    const { user, loading } = useAuth()
    const { pathname } = useLocation()
    if (loading) return <div className="p-6 text-sm text-ink-sub">불러오는 중...</div>
    if (!user) return <Navigate to="/login" replace />
    // 첫 로그인(또는 관리자가 초기화한 계정)은 비밀번호를 바꾸기 전까지 다른 화면에 못 들어간다
    if (user.must_change_password && pathname !== '/change-password') {
        return <Navigate to="/change-password" replace />
    }
    return <Outlet />
}