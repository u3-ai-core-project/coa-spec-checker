import { apiFetch } from './client'
import type { LoginResult, Me } from '../types/auth'

export function login(username: string, password: string) {
    return apiFetch<LoginResult>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    })
}

export function fetchMe() {
    return apiFetch<Me>('/auth/me', {
        method: 'GET',
    })
}

export function changePassword(currentPassword: string, newPassword: string) {
    return apiFetch<Me>('/auth/password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
}