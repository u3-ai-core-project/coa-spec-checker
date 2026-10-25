import { useEffect, useState } from 'react'
import { ApiError } from '../../../api/client'
import { fetchDashboardSummary } from '../api'
import type { DashboardQuery, DashboardSummary } from '../types'

interface Loaded {
    key: string
    data: DashboardSummary | null
    error: string | null
}

export function useDashboardSummary({ userId, from, to }: DashboardQuery) {
    const [reloadCount, setReloadCount] = useState(0)
    const [loaded, setLoaded] = useState<Loaded | null>(null)
    const key = `${userId ?? ''}|${from ?? ''}|${to ?? ''}|${reloadCount}`

    useEffect(() => {
        let cancelled = false
        fetchDashboardSummary({ userId, from, to })
            .then((data) => {
                if (!cancelled) setLoaded({ key, data, error: null })
            })
            .catch((e: unknown) => {
                if (cancelled) return
                const message =
                    e instanceof ApiError ? e.message : '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
                setLoaded({ key, data: null, error: message })
            })
        return () => { cancelled = true }
    }, [key, userId, from, to])

    // 필터가 바뀌어 새 요청이 진행 중이면 loading
    const current = loaded?.key === key ? loaded : null
    return {
        data: current?.data ?? null,
        error: current?.error ?? null,
        loading: current === null,
        reload: () => setReloadCount((n) => n + 1),
    }
}