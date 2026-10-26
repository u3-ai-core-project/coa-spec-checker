import { useEffect, useRef, useState } from 'react'
import { api } from '../../review/shared/api'
import type { FollowUpsResponse } from '../../review/shared/api/types'
import type { BatchQueueItem } from '../../upload/batchTypes'

// 문의가 필요한 로트: 부적합(1), 서류 불일치(2), 판정 불가·누락·확인 필요(3)
export const needsFollowUp = (i: BatchQueueItem) => i.priority >= 1 && i.priority <= 3

// 값이 null이면 요청에 실패한 문서
export function useFollowUps(items: BatchQueueItem[]) {
    const key = items.filter(needsFollowUp).map((i) => i.document_id).join(',')
    const requested = useRef(new Set<string>())
    const [map, setMap] = useState<Record<string, FollowUpsResponse | null>>({})

    useEffect(() => {
        const need = (key ? key.split(',') : []).filter((id) => !requested.current.has(id))
        if (need.length === 0) return
        need.forEach((id) => requested.current.add(id))
        void Promise.allSettled(need.map((id) => api.getFollowUps(id))).then((results) => {
            setMap((prev) => {
                const next = { ...prev }
                results.forEach((r, i) => {
                    next[need[i]] = r.status === 'fulfilled' ? r.value : null
                })
                return next
            })
        })
    }, [key])

    const ids = key ? key.split(',') : []
    return { map, loading: ids.some((id) => !(id in map)) }
}