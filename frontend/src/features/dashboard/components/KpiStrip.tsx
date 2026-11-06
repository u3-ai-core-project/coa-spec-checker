import type { ReactNode } from 'react'
import { formatDuration, formatPercent } from '../lib/format'
import type { DashboardSummary } from '../types'

const VALUE = 'text-[26px] font-bold leading-tight text-ink'

function Cell({ label, first = false, children }: { label: string; first?: boolean; children: ReactNode }) {
    return (
        <div className={`flex min-w-0 flex-col gap-1 px-5 pb-3 pt-3.5 ${first ? '' : 'border-l border-line'}`}>
            <span className="text-xs font-medium text-ink-sub">{label}</span>
            {children}
        </div>
    )
}

function Bar({ parts }: { parts: { ratio: number; color: string }[] }) {
    return (
        <div className="flex h-1.5 w-[100px] shrink-0 overflow-hidden rounded-full bg-[#eceef1]">
            {parts.map((p) => (
                <div key={p.color} className={`h-full ${p.color}`} style={{ width: `${Math.min(100, Math.max(0, p.ratio))}%` }} />
            ))}
        </div>
    )
}

interface Props {
    data: DashboardSummary | null
}

export default function KpiStrip({ data }: Props) {
    const passCount = data ? data.accept_count + data.conditional_accept_count : 0
    const autoRate = data?.auto_approve_rate
    return (
        <div className="grid grid-cols-[170fr_200fr_210fr_200fr_200fr_172fr] overflow-hidden rounded-xl border border-line bg-white">
            <Cell label="최근 처리 건수" first>
                <span className={VALUE}>{data ? `${data.total_processed}건` : '—'}</span>
            </Cell>

            <Cell label="합격률">
                <span className={VALUE}>{data ? formatPercent(data.pass_rate) : '—'}</span>
                {data && (
                    <div className="flex items-center gap-2 text-xs text-ink-sub">
                        <Bar parts={[{ ratio: data.pass_rate, color: 'bg-[#1a7f4b]' }]} />
                        {passCount} / {data.total_processed}건
                    </div>
                )}
            </Cell>

            <Cell label="평균 검수 소요 시간">
                <div className="flex flex-wrap items-end gap-x-1.5">
                    <span className={`${VALUE} whitespace-nowrap`}>{data ? formatDuration(data.avg_processing_time_sec) : '—'}</span>
                    {data && <span className="whitespace-nowrap pb-1 text-xs text-ink-sub">건당 평균</span>}
                </div>
            </Cell>

            <Cell label="정상 자동 처리율">
                <span className={VALUE}>{autoRate !== undefined ? formatPercent(autoRate) : '—'}</span>
                <span className="text-xs text-ink-sub">{autoRate !== undefined ? '승인 문서 기준' : '서버 반영 전'}</span>
            </Cell>

            <Cell label="AI 권고 일치율">
                <span className={VALUE}>{data ? formatPercent(data.recommendation_match_rate) : '—'}</span>
                <span className="text-xs text-ink-sub">보류 권고 제외</span>
            </Cell>

            <Cell label="보류 중">
                <span className={VALUE}>{data ? `${data.on_hold_count}건` : '—'}</span>
            </Cell>
        </div>
    )
}