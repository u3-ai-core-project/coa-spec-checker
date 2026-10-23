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