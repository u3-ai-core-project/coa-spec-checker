export type Role = 'USER' | 'ADMIN'

export interface ApiErrorBody {
    code: string
    message: string
}

export interface ApiResponse<T> {
    success: boolean
    data: T | null
    error?: ApiErrorBody | null
}

export interface LoginResult {
    access_token: string
    token_type: string
    expires_in: number
    user: { id: number, name: string, role: Role }
}

export interface Me {
    id: number
    username: string
    name: string
    role: Role
}