import { apiFetch } from '../../api/client'
import type { DashboardQuery, DashboardSummary, UserOption } from './types'

export function fetchDashboardSummary({ userId, materialCode, from, to }: DashboardQuery = {}) {
    const params = new URLSearchParams()
    if (userId !== undefined) params.set('user_id', String(userId))
    if (materialCode) params.set('material_code', materialCode)
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    const query = params.toString()
    return apiFetch<DashboardSummary>(`/dashboard/summary${query ? `?${query}` : ''}`)
}

export function fetchUsers() {
    return apiFetch<UserOption[]>('/users')
}