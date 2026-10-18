export type Role = 'USER' | 'ADMIN'

// TODO: 로그인 API 연결 후 GET /auth/me 응답으로 교체
export const CURRENT_USER: { name: string; role: Role } = {
    name: '김OO',
    role: "USER",
}