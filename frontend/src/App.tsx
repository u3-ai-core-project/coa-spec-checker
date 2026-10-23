import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import AuthProvider from './auth/AuthProvider'
import RequireAuth from './auth/RequireAuth'
import LoginPage from './pages/LoginPage'
import { NAV_ITEMS } from './navigation'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              {NAV_ITEMS.map((item) => (
                <Route
                  key={item.path}
                  path={item.path}
                  element={
                    <div className="rounded-xl border border-line bg-white p-6 text-sm text-ink-sub">
                      {item.label} 화면은 아직 구현 전입니다.
                    </div>
                  }
                />
              ))}
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}