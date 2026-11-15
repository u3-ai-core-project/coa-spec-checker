import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { setOnUnauthorized, tokenStorage } from '../api/client'
import type { Me } from '../types/auth'
import { AuthContext } from './authContext'
import { changePassword as changePasswordApi, fetchMe, login as loginApi } from '../api/auth'

export default function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<Me | null>(null)
    const [loading, setLoading] = useState(() => tokenStorage.get() !== null)

    useEffect(() => {
        setOnUnauthorized(() => setUser(null))
    }, [])

    // 새로고침해도 로그인이 유지되도록, 저장된 토큰으로 내 정보를 다시 가져옴
    useEffect(() => {
        if (tokenStorage.get() === null) return
        fetchMe()
            .then(setUser)
            .catch(() => tokenStorage.clear())
            .finally(() => setLoading(false))
    }, [])

    const login = useCallback(async (username: string, password: string) => {
        const result = await loginApi(username, password)
        tokenStorage.set(result.access_token)
        try {
            setUser(await fetchMe())
        } catch (e) {
            tokenStorage.clear()
            throw e
        }
    }, [])

    const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
        await changePasswordApi(currentPassword, newPassword)
        if (user) {
            setUser({ ...user, must_change_password: false })
        }
    }, [])

    const logout = useCallback(() => {
        tokenStorage.clear()
        setUser(null)
    }, [])

    const value = useMemo(() => ({ user, loading, login, logout, changePassword }), [user, loading, login, logout, changePassword])
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}