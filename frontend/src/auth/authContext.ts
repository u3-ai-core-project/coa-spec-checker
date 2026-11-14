import { createContext, useContext } from 'react'
import type { Me } from '../types/auth'

export interface AuthState {
    user: Me | null
    loading: boolean
    login: (username: string, password: string) => Promise<void>
    logout: () => void
    changePassword: (currentPassword: string, newPassword: string) => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
    const ctx = useContext(AuthContext)
    if (!ctx) throw new Error('userAuth는 AuthProtivder 안에서만 사용할 수 있습니다.')
    return ctx
}