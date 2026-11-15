import type { ReactNode } from 'react'
import { ChevronDownIcon } from '../../../components/icons'
import { PERIOD_OPTIONS, type PeriodKey, type ReportFilters } from '../lib/filters'

const SELECT = 'h-full appearance-none bg-transparent pl-1.5 pr-9 text-[13px] font-medium text-ink outline-none'

function Box({ label, children }: { label: string; children: ReactNode }) {
    return (
        <label className="relative flex h-9 items-center rounded-lg border border-[#cfd4da] bg-white pl-3.5 text-[13px] font-medium text-ink">
            <span>{label}</span>
            {children}
            <ChevronDownIcon className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2" />
        </label>
    )
}

const DECISION_OPTIONS: { value: ReportFilters['decision']; label: string }[] = [
    { value: 'all', label: '전체' },
    { value: 'accept', label: '승인' },
    { value: 'reject', label: '불합격' },
    { value: 'conditional_accept', label: '조건부 승인' },
]

const RECOMMENDATION_OPTIONS: { value: ReportFilters['recommendation']; label: string }[] = [
    { value: 'all', label: '전체' },
    { value: 'reject', label: '불합격' },
    { value: 'approve', label: '승인' },
    { value: 'hold', label: '보류' },
]

interface Props {
    filters: ReportFilters
    onChange: (filters: ReportFilters) => void
}

export default function FilterBar({ filters, onChange }: Props) {
    return (
        <div className="flex flex-wrap items-center gap-2.5">
            <Box label="기간:">
                <select
                    className={SELECT}
                    value={filters.period}
                    onChange={(e) => onChange({ ...filters, period: e.target.value as PeriodKey })}
                    aria-label="기간"
                >
                    {PERIOD_OPTIONS.map((o) => (
                        <option key={o.key} value={o.key}>
                            {o.label}
                        </option>
                    ))}
                </select>
            </Box>

            <Box label="처분 결과:">
                <select
                    className={SELECT}
                    value={filters.decision}
                    onChange={(e) => onChange({ ...filters, decision: e.target.value as ReportFilters['decision'] })}
                    aria-label="처분 결과"
                >
                    {DECISION_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                            {o.label}
                        </option>
                    ))}
                </select>
            </Box>

            <Box label="AI 권고:">
                <select
                    className={SELECT}
                    value={filters.recommendation}
                    onChange={(e) => onChange({ ...filters, recommendation: e.target.value as ReportFilters['recommendation'] })}
                    aria-label="AI 권고"
                >
                    {RECOMMENDATION_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                            {o.label}
                        </option>
                    ))}
                </select>
            </Box>

            <label className="flex h-9 items-center gap-2 rounded-lg border border-[#cfd4da] bg-white px-3.5 text-[13px] font-medium text-ink">
                <input
                    type="checkbox"
                    checked={filters.mismatchOnly}
                    onChange={(e) => onChange({ ...filters, mismatchOnly: e.target.checked })}
                    className="h-4 w-4 accent-brand"
                />
                권고 ≠ 처분
            </label>
        </div>
    )
}