export type PeriodKey = 'all' | '7d' | '30d' | 'custom'

export const PERIOD_OPTIONS: { key: PeriodKey; label: string }[] = [
    { key: 'all', label: '전체 기간' },
    { key: '7d', label: '최근 7일' },
    { key: '30d', label: '최근 30일' },
    { key: 'custom', label: '직접 선택' },
]

const seoulDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' })

export function resolveRange(key: PeriodKey, custom: { from: string; to: string }) {
    if (key === 'all') return {}
    if (key === 'custom') return { from: custom.from || undefined, to: custom.to || undefined }
    const days = key === '7d' ? 7 : 30
    const now = new Date()
    const start = new Date(now.getTime() - (days - 1) * 24 * 60 * 60 * 1000)
    return { from: seoulDate.format(start), to: seoulDate.format(now) }
}