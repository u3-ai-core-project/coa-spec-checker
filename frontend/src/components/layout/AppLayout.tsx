import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'

export default function AppLayout() {
    return (
        <div className="flex h-screen bg-white text-ink">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
                <Header />
                <main className="flex-1 overflow-auto bg-surface p-6">
                    <Outlet />
                </main>
            </div>
        </div>
    )
}