import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/authContext'

export default function LoginPage() {
    const { user, login } = useAuth()
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)

    if (user) return <Navigate to="/dashboard" replace />

    async function handleSubmit(e: FormEvent) {
        e.preventDefault()
        setError(null)
        setSubmitting(true)
        try {
            await login(username, password)
        } catch (err) {
            setError(
                err instanceof ApiError && err.code === 'INVALID_CREDENTIALS'
                    ? '아이디 또는 비밀번호가 올바르지 않습니다.'
                    : '로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.',
            )
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-surface p-6">
            <form
                onSubmit={handleSubmit}
                className="w-full max-w-md rounded-xl border border-line bg-white p-10"
            >
                <p className="text-sm font-bold text-brand">CoA Inspector</p>
                <h1 className="mt-6 text-xl font-bold text-ink">로그인</h1>

                <label htmlFor="username" className="mt-5 block text-sm text-ink-sub">
                    아이디
                </label>
                <input
                    id="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    required
                    className={`mt-2 w-full rounded-md border px-3 py-3 text-sm text-ink-sub outline-none ${error ? 'border-red-500' : 'border-line focus:border-brand'
                        }`}
                />

                <label htmlFor="password" className="mt-4 block text-sm text-ink-sub">
                    비밀번호
                </label>
                <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                    className={`mt-2 w-full rounded-md border px-3 py-3 text-sm text-ink-sub outline-none ${error ? 'border-red-500' : 'border-line focus:border-brand'
                        }`}
                />

                {error && (
                    <p role="alert" className="mt-2 text-xs text-red-600">
                        {error}
                    </p>
                )}

                <button
                    type="submit"
                    disabled={submitting}
                    className="mt-4 w-full rounded-md bg-brand py-3 text-sm text-white hover:opacity-90 disabled:opacity-50"
                >
                    {submitting ? '로그인 중...' : '로그인'}
                </button>
            </form>
        </div>
    )
}