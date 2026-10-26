import { useEffect, useState } from 'react'
import { ApiError } from '../../../api/client'
import { fetchBatch } from '../../upload/batchApi'
import type { BatchDetail } from '../../upload/batchTypes'

const POLL_MS = 3000

interface Loaded {
    id: string
    data: BatchDetail | null
    error: string | null
}

export function useBatch(batchId: string) {
    const [state, setState] = useState<Loaded | null>(null)
    const [reloadCount, setReloadCount] = useState(0)

    useEffect(() => {
        if (!batchId) return
        let cancelled = false
        let timer: ReturnType<typeof setTimeout> | undefined

        async function load() {
            try {
                const data = await fetchBatch(batchId)
                if (cancelled) return
                setState({ id: batchId, data, error: null })
                if (data.summary.processing > 0) timer = setTimeout(load, POLL_MS) // 처리 중이 남았으면 다시
            } catch (e) {
                if (cancelled) return
                const message = e instanceof ApiError ? e.message : '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
                // 갱신이 실패해도 이미 받은 화면은 그대로 두고 오류만 알림
                setState((prev) => ({ id: batchId, data: prev?.id === batchId ? prev.data : null, error: message }))
            }
        }
        void load()
        return () => {
            cancelled = true
            if (timer) clearTimeout(timer)
        }
    }, [batchId, reloadCount])

    const current = state?.id === batchId ? state : null
    return {
        data: current?.data ?? null,
        error: current?.error ?? null,
        loading: batchId !== '' && current === null,
        reload: () => setReloadCount((n) => n + 1),
    }
}