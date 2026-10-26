import type { ReactNode } from 'react'
import type { BatchSummary } from '../../upload/batchTypes'

const VALUE = 'text-[26px] font-bold leading-tight text-ink'

function Cell({ label, dot, children }: { label: string; dot?: string; children: ReactNode }) {
    return (
        <div className="flex min-w-0 flex-col gap-1 border-l border-line px-5 pb-3 pt-3.5 first:border-l-0">
            <span className="flex items-center gap-1.5 text-xs font-medium text-ink-sub">
                {dot && <span className="h-2 w-2 rounded-full" style={{ backgroundColor: dot }} />}
                {label}
            </span>
            {children}
        </div>
    )
}

function Count({ n }: { n: number }) {
    return (
        <span className={VALUE}>
            {n}
            <span className="ml-1 text-xs font-normal text-ink-sub">건</span>
        </span>
    )
}

export default function BatchKpi({ summary }: { summary: BatchSummary }) {
    const hold = summary.hold + summary.document_issue // 보류 권고: 서류 불일치도 보류 사유
    const wait = summary.processing + summary.isolated // 대기·오류
    const parts = [
        { n: summary.approve, color: '#1a7f4b' },
        { n: hold, color: '#e3a008' },
        { n: summary.reject, color: '#c0392b' },
        { n: wait, color: '#cfd4da' },
    ]
    return (
        <div className="grid grid-cols-[1.3fr_1fr_1fr_1fr_1.2fr] overflow-hidden rounded-xl border border-line bg-white">
            <Cell label="배치 전체">
                <span className={VALUE}>
                    {summary.total}
                    <span className="ml-1 text-xs font-normal text-ink-sub">로트</span>
                </span>
                <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-[#eceef1]">
                    {summary.total > 0 &&
                        parts.map((p) => <div key={p.color} className="h-full" style={{ width: `${(p.n / summary.total) * 100}%`, backgroundColor: p.color }} />)}
                </div>
            </Cell>
            <Cell label="승인 권고" dot="#1a7f4b">
                <Count n={summary.approve} />
            </Cell>
            <Cell label="보류 권고" dot="#e3a008">
                <Count n={hold} />
            </Cell>
            <Cell label="불합격 권고" dot="#c0392b">
                <Count n={summary.reject} />
            </Cell>
            <Cell label="AI 분석 대기·오류" dot="#9aa0a8">
                <Count n={wait} />
            </Cell>
        </div>
    )
}