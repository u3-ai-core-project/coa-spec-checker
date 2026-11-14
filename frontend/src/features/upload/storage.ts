import { useEffect, useState } from 'react'
import { apiFetch } from '../../api/client'

// GET /storage: 로그인한 누구나 볼 수 있는 저장 공간 단계
export interface StorageStatus {
    level: 'ok' | 'warn' | 'block'
    reason?: 'quota' | 'disk' | null // block 이유: 설정 한도 / 서버 디스크 부족
    used_percent: number
}

export function useStorageStatus() {
    const [status, setStatus] = useState<StorageStatus | null>(null)
    useEffect(() => {
        let alive = true
        apiFetch<StorageStatus>('/storage')
            .then((s) => { if (alive) setStatus(s) })
            .catch(() => { /* 옛 서버이거나 실패하면 안내만 생략하고 업로드는 막지 않는다 */ })
        return () => { alive = false }
    }, [])
    return status
}