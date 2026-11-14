import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/authContext'

// 서버 규칙과 같게: 8자 이상, 영문 1개 이상 + 숫자 1개 이상, 72바이트 이하 (한글 1자 = 3바이트)
function checkRule(pw: string): string | null {
    if (pw.length < 8) return '8자 이상이어야 합니다.'
    if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return '영문자와 숫자를 각각 1개 이상 포함해야 합니다.'
    if (new TextEncoder().encode(pw).length > 72) return '너무 깁니다. (72바이트 이하, 한글 1자는 3바이트)'
    return null
}

const SERVER_MESSAGES: Record<string, string> = {
    WRONG_PASSWORD: '현재 비밀번호가 올바르지 않습니다.',
    INVALID_PASSWORD: '새 비밀번호가 규칙에 맞지 않거나 현재 비밀번호와 같습니다.',
}

export default function ChangePasswordPage() {
    const { user, changePassword, logout } = useAuth()
    const [current, setCurrent] = useState('')
    const [next, setNext] = useState('')
    const [confirm, setConfirm] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)
    const [done, setDone] = useState(false)

    if (done) return <Navigate to="/login" replace state={{ passwordChanged: true }} />
    if (!user) return <Navigate to="/login" replace />

    async function handleSubmit(e: FormEvent) {
        e.preventDefault()
        const ruleError = checkRule(next)
        if (ruleError) return setError(ruleError)
        if (next !== confirm) return setError('새 비밀번호 확인이 일치하지 않습니다.')
        setError(null)
        setSubmitting(true)
        try {
            await changePassword(current, next)
            logout() // 새 비밀번호로 다시 로그인하게 함
            setDone(true) // 로그인 화면으로 이동하며 "변경되었습니다" 안내를 띄움
        } catch (err) {
            setError(
                err instanceof ApiError && SERVER_MESSAGES[err.code]
                    ? SERVER_MESSAGES[err.code]
                    : '비밀번호를 바꾸지 못했습니다. 잠시 후 다시 시도해 주세요.',
            )
        } finally {
            setSubmitting(false)
        }
    }

    const field = 'mt-2 w-full rounded-md border border-line px-3 py-3 text-sm text-ink outline-none focus:border-brand'

    return (
        <div className="flex min-h-screen items-center justify-center bg-surface p-6">
            <form onSubmit={handleSubmit} className="w-full max-w-md rounded-xl border border-line bg-white p-10">
                <p className="text-sm font-bold text-brand">CoA Inspector</p>
                <h1 className="mt-6 text-xl font-bold text-ink">비밀번호 변경</h1>
                <p className="mt-2 text-sm leading-relaxed text-ink-sub [word-break:keep-all]">
                    {user.must_change_password ? (
                        <>
                            처음 로그인했거나 관리자가 비밀번호를 초기화했습니다.
                            <br />
                            새 비밀번호로 바꿔야 서비스를 쓸 수 있습니다.
                        </>
                    ) : (
                        '새 비밀번호를 입력해 주세요.'
                    )}
                </p>

                <label htmlFor="current" className="mt-5 block text-sm text-ink-sub">현재 비밀번호</label>
                <input id="current" type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
                    autoComplete="current-password" required className={field} />

                <label htmlFor="next" className="mt-4 block text-sm text-ink-sub">새 비밀번호</label>
                <input id="next" type="password" value={next} onChange={(e) => setNext(e.target.value)}
                    autoComplete="new-password" required className={field} />
                <p className="mt-1 text-xs text-ink-sub [word-break:keep-all]">8자 이상, 영문자와 숫자를 각각 1개 이상 포함</p>

                <label htmlFor="confirm" className="mt-4 block text-sm text-ink-sub">새 비밀번호 확인</label>
                <input id="confirm" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                    autoComplete="new-password" required className={field} />

                {error && <p role="alert" className="mt-2 text-xs text-red-600">{error}</p>}

                <button type="submit" disabled={submitting}
                    className="mt-4 w-full rounded-md bg-brand py-3 text-sm text-white hover:opacity-90 disabled:opacity-50">
                    {submitting ? '변경 중...' : '비밀번호 변경'}
                </button>
                <button type="button" onClick={logout} className="mt-3 w-full text-xs text-ink-sub underline">
                    로그아웃
                </button>
            </form>
        </div>
    )
}