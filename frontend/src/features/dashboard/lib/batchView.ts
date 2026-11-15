import type { BatchDetail, BatchQueueItem } from '../../upload/batchTypes'

export type TabKey = 'all' | 'reject' | 'issue' | 'hold' | 'ok' | 'wait'

// 서버 priority: 1 부적합, 2 서류 불일치, 3 판정 불가·누락·확인 필요, 4 정상, 5 처리 중, 0 격리
export const TABS: { key: TabKey; label: string; match: (priority: number) => boolean }[] = [
    { key: 'all', label: '전체', match: () => true },
    { key: 'reject', label: '부적합', match: (p) => p === 1 },
    { key: 'issue', label: '서류 불일치', match: (p) => p === 2 },
    { key: 'hold', label: '판정 불가·누락', match: (p) => p === 3 },
    { key: 'ok', label: '정상', match: (p) => p === 4 },
    { key: 'wait', label: '대기·오류', match: (p) => p === 5 || p === 0 },
]

export const PRIORITY_COLOR: Record<number, string> = {
    1: '#c0392b',
    2: '#9a6a1a',
    3: '#6a4fc9',
    4: '#1a7f4b',
    5: '#9aa0a8',
    0: '#9aa0a8',
}

// 검토 큐와 격리 목록을 한 줄로 합침
export function allItems(d: BatchDetail): BatchQueueItem[] {
    return [...d.queue, ...d.isolated]
}

const kst = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
})

// 서버 시각을 한국 시간 "2026-10-25 14:20"으로. 시간대 표시가 없으면 UTC로 본다(서버 저장 방식은 확인 필요)
export function formatKst(iso: string): string {
    const hasZone = /Z$|[+-]\d{2}:?\d{2}$/.test(iso)
    return kst.format(new Date(hasZone ? iso : iso + 'Z'))
}