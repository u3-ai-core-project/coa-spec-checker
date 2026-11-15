// [개발 확인용 임시 코드] 로그인 화면은 다른 파트의 몫입니다. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { errorMessage } from '../features/review/shared/api/errors';
import { USE_MOCK } from '../features/review/shared/config';
import { REVIEW_PATH } from '../features/review/shared/domain/constants';
import '../features/review/shell/fonts';
import { useAuth } from './authState';

/** 개발 화면을 띄우는 데 필요한 최소한의 임시 로그인 화면입니다. */
export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? REVIEW_PATH;
  if (user) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="coa-font flex min-h-screen items-center justify-center bg-[#F4F5F7] text-[#1F2328]">
      <form onSubmit={submit} className="flex w-[360px] flex-col gap-4 rounded-2xl border border-[#E3E5E8] bg-white p-8">
        <h1 className="text-[18px] font-bold text-[#2B4FCB]">CoA Inspector</h1>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold">
          아이디
          <input
            className="h-10 rounded-lg border border-[#D0D4DA] px-3 text-[14px] font-normal"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold">
          비밀번호
          <input
            className="h-10 rounded-lg border border-[#D0D4DA] px-3 text-[14px] font-normal"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <p className="text-[12px] text-[#C0342E]">{error}</p>}
        <button
          type="submit"
          disabled={busy || !username || !password}
          className="h-10 rounded-lg bg-[#2B4FCB] text-[14px] font-semibold text-white disabled:bg-[#E3E5E8] disabled:text-[#8A9099]"
        >
          로그인
        </button>
        {USE_MOCK && (
          <p className="text-[12px] leading-relaxed text-[#8A9099]">
            목업 계정입니다. 사용자는 user / user, 관리자는 admin / admin으로 로그인합니다.
          </p>
        )}
      </form>
    </div>
  );
}
