import type { ApiResponse } from '../types/auth'

const BASE_URL = `${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api/v1`
const TOKEN_KEY = 'coa_access_token'

export const tokenStorage = {
    get: () => localStorage.getItem(TOKEN_KEY),
    set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
    clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
    code: string
    status: number

    constructor(code: string, message: string, status: number) {
        super(message)
        this.code = code
        this.status = status
    }
}

// 401 UNAUTHORIZED를 받았을 때 실행할 동작을 앱에서 등록함
let onUnauthorized: (() => void) | null = null
export const setOnUnauthorized = (callback: () => void) => {
    onUnauthorized = callback
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers)
    if (options.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json')
    }

    const token = tokenStorage.get()
    if (token) headers.set('Authorization', `Bearer ${token}`)

    const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

    let body: ApiResponse<T> | null = null
    try {
        body = await res.json()
    } catch {
        // 응답이 JSON이 아닌 경우
    }

    if (res.status === 401 && body?.error?.code === 'UNAUTHORIZED') {
        tokenStorage.clear()
        onUnauthorized?.()
    }

    if (!res.ok || !body?.success) {
        throw new ApiError(body?.error?.code ?? 'UNKNOWN', body?.error?.message ?? '요청에 실패했습니다.', res.status)
    }
    return body.data as T
}