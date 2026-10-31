import type { DocumentListItem } from '../../review/shared/api/types'

export type Decision = NonNullable<DocumentListItem['final_decision']>
export type Recommendation = NonNullable<DocumentListItem['lot_recommendation']>

export type PeriodKey = '7d' | '30d' | '90d' | 'all'

export const PERIOD_OPTIONS: { key: PeriodKey; label: string }[] = [
    { key: '7d', label: '최근 7일' },
    { key: '30d', label: '최근 30일' },
    { key: '90d', label: '최근 90일' },
    { key: 'all', label: '전체 기간' },
]

export interface ReportFilters {
    period: PeriodKey
    decision: 'all' | Decision
    recommendation: 'all' | Recommendation
    mismatchOnly: boolean
}

export const DEFAULT_FILTERS: ReportFilters = {
    period: '30d',
    decision: 'all',
    recommendation: 'all',
    mismatchOnly: false,
}

const PERIOD_DAYS: Record<PeriodKey, number | null> = { '7d': 7, '30d': 30, '90d': 90, all: null }


export function isMismatch(item: DocumentListItem): boolean {
    return !(
        (item.lot_recommendation === 'approve' && item.final_decision === 'accept') ||
        (item.lot_recommendation === 'reject' && item.final_decision === 'reject')
    )
}

// 처분 일시 최신순으로 정렬
export function filterReports(items: DocumentListItem[], filters: ReportFilters): DocumentListItem[] {
    const days = PERIOD_DAYS[filters.period]
    const since = days === null ? null : Date.now() - days * 24 * 60 * 60 * 1000
    const time = (item: DocumentListItem) => (item.approved_at ? Date.parse(item.approved_at) : 0)

    return items
        .filter((item) => since === null || time(item) >= since)
        .filter((item) => filters.decision === 'all' || item.final_decision === filters.decision)
        .filter((item) => filters.recommendation === 'all' || item.lot_recommendation === filters.recommendation)
        .filter((item) => !filters.mismatchOnly || isMismatch(item))
        .sort((a, b) => time(b) - time(a))
}