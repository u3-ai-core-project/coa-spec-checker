import { useEffect, useState } from 'react'
import { api } from '../../review/shared/api'
import type { DocumentListItem } from '../../review/shared/api/types'

interface Loaded {
    key: number
    items: DocumentListItem[]
    error: string | null
}

const NO_ITEMS: DocumentListItem[] = []

export function useReports() {
    const [reloadCount, setReloadCount] = useState(0)
    const [loaded, setLoaded] = useState<Loaded | null>(null)
    const [reasons, setReasons] = useState<Record<string, string>>({})

    useEffect(() => {
        let cancelled = false
        api.listDocuments({ status: 'approved', size: 100 })
            .then((result) => {
                if (!cancelled) setLoaded({ key: reloadCount, items: result.items, error: null })
            })
            .catch((e: unknown) => {
                if (cancelled) return
                const message = e instanceof Error ? e.message : '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
                setLoaded({ key: reloadCount, items: NO_ITEMS, error: message })
            })
        return () => {
            cancelled = true
        }
    }, [reloadCount])

    const items = loaded?.items ?? NO_ITEMS

    // 사유(decision_reason)는 목록에 없어서 문서마다 상세를 불러 채운다. 서버 목록에 필드가 생기면 이 부분을 뺀다
    useEffect(() => {
        let cancelled = false
        const ids = items.map((item) => item.document_id)
        Promise.allSettled(ids.map((id) => api.getDocument(id))).then((results) => {
            if (cancelled) return
            const next: Record<string, string> = {}
            results.forEach((result, index) => {
                if (result.status === 'fulfilled' && result.value.decision_reason) {
                    next[ids[index]] = result.value.decision_reason
                }
            })
            setReasons(next)
        })
        return () => {
            cancelled = true
        }
    }, [items])

    return {
        items,
        reasons,
        loading: loaded?.key !== reloadCount,
        error: loaded?.key === reloadCount ? loaded.error : null,
        reload: () => setReloadCount((n) => n + 1),
    }
}