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
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
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

// 파일(엑셀 등)을 받는 호출
export async function apiDownload(path: string): Promise<{ blob: Blob; fileName: string | null }> {
    const headers = new Headers()
    const token = tokenStorage.get()
    if (token) headers.set('Authorization', `Bearer ${token}`)

    const res = await fetch(`${BASE_URL}${path}`, { headers })

    if (!res.ok) {
        // 실패하면 서버가 JSON 오류를 줌 (예: 409 NOT_READY, 500 REPORT_GENERATION_FAILED)
        let body: ApiResponse<unknown> | null = null
        try {
            body = await res.json()
        } catch {
            // JSON이 아닌 경우
        }
        if (res.status === 401 && body?.error?.code === 'UNAUTHORIZED') {
            tokenStorage.clear()
            onUnauthorized?.()
        }
        throw new ApiError(body?.error?.code ?? 'UNKNOWN', body?.error?.message ?? '요청에 실패했습니다.', res.status)
    }

    return { blob: await res.blob(), fileName: parseFileName(res.headers.get('Content-Disposition')) }
}

// Content-Disposition에서 한글 파일명(filename*)을 꺼냄. 없으면 일반 filename, 그것도 없으면 null
function parseFileName(disposition: string | null): string | null {
    if (!disposition) return null
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
    if (encoded) {
        try {
            return decodeURIComponent(encoded[1])
        } catch {
            // 디코딩이 안 되면 아래 일반 filename으로 넘어간다
        }
    }
    const plain = /filename="?([^";]+)"?/i.exec(disposition)
    return plain ? plain[1] : null
}