import { BrowserRouter, Navigate, Route, Routes, useRoutes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import AuthProvider from './auth/AuthProvider'
import RequireAuth from './auth/RequireAuth'
import LoginPage from './pages/LoginPage'
import { NAV_ITEMS } from './navigation'
import { useAuth } from './auth/authContext'
import { CurrentUserProvider } from './features/review/shared/currentUser'
import { reviewRoutes } from './features/review/routes'
import { specsRoutes } from './features/specs/routes'
import UploadPage from './features/upload/UploadPage'
import DashboardPage from './features/dashboard/DashboardPage'
import BatchPage from './features/dashboard/BatchPage'
import ReportsPage from './features/reports/ReportsPage'

function ReviewSpecsRoutes() {
  const { user } = useAuth()
  const element = useRoutes([...reviewRoutes, ...specsRoutes])
  if (!user) return null
  return <CurrentUserProvider value={user}>{element}</CurrentUserProvider>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/upload" replace />} />
              {NAV_ITEMS.filter((item) => !['/upload', '/inspection', '/specs', '/dashboard', '/reports'].includes(item.path)).map((item) => (
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
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/dashboard/batches/:batchId" element={<BatchPage />} />
              <Route path="*" element={<ReviewSpecsRoutes />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}