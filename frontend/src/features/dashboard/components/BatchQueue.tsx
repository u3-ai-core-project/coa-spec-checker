import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RecommendationBadge, StatusBadge } from '../../review/shared/components/badges'
import type { BatchQueueItem } from '../../upload/batchTypes'
import { queueReason } from '../../upload/lib/batchText'
import { PRIORITY_COLOR, TABS, type TabKey } from '../lib/batchView'

const GRID = 'grid grid-cols-[40px_96px_84px_120px_minmax(0,1fr)_130px_76px] items-center gap-2 px-5'
const OPENABLE = ['extracted', 'in_review', 'on_hold', 'approved'] // 검수 화면을 열 수 있는 상태

export default function BatchQueue({ items }: { items: BatchQueueItem[] }) {
    const navigate = useNavigate()
    const [tab, setTab] = useState<TabKey>('all')
    const current = TABS.find((t) => t.key === tab) ?? TABS[0]
    const shown = items.filter((i) => current.match(i.priority))

    return (
        <section className="overflow-hidden rounded-xl border border-line bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <h2 className="text-[15px] font-bold text-ink">우선순위 큐</h2>
                <div className="flex flex-wrap gap-1.5">
                    {TABS.map((t) => {
                        const n = items.filter((i) => t.match(i.priority)).length
                        const active = t.key === tab
                        return (
                            <button
                                key={t.key}
                                type="button"
                                onClick={() => setTab(t.key)}
                                className={`rounded-md border px-2.5 py-1 text-xs font-medium ${active ? 'border-brand bg-brand text-white' : 'border-line bg-white text-ink'}`}
                            >
                                {t.label} <span className={active ? '' : 'text-[#9aa0a8]'}>{n}</span>
                            </button>
                        )
                    })}
                </div>
            </div>

            <div className={`${GRID} border-y border-line bg-[#f7f8fa] py-2.5 text-xs font-bold text-ink-sub`}>
                <span>순위</span>
                <span>로트</span>
                <span>협력사</span>
                <span>분류</span>
                <span>사유</span>
                <span>AI 권고</span>
                <span>상태</span>
            </div>

            {shown.length === 0 ? (
                <p className="py-10 text-center text-[13px] text-[#9aa0a8]">해당하는 로트가 없습니다.</p>
            ) : (
                shown.map((item, idx) => {
                    const openable = OPENABLE.includes(item.status)
                    return (
                        <div
                            key={item.document_id}
                            role={openable ? 'button' : undefined}
                            tabIndex={openable ? 0 : undefined}
                            onClick={() => openable && navigate(`/inspection/${item.document_id}`)}
                            onKeyDown={(e) => {
                                if (openable && e.key === 'Enter') navigate(`/inspection/${item.document_id}`)
                            }}
                            className={`${GRID} border-b border-[#eceef1] py-3 last:border-b-0 ${openable ? 'cursor-pointer hover:bg-surface' : ''} ${item.status === 'approved' ? 'opacity-60' : ''}`}
                        >
                            <span className="text-xs text-ink-sub">{idx + 1}</span>
                            <span className="truncate text-[13px] font-bold text-ink">{item.lot_no ?? item.received_lot_no ?? '-'}</span>
                            <span className="truncate text-xs text-ink-sub">{item.supplier ?? '-'}</span>
                            <span className="flex items-center gap-1.5 text-xs text-ink">
                                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: PRIORITY_COLOR[item.priority] ?? '#9aa0a8' }} />
                                {item.priority_label}
                            </span>
                            <span className="text-xs text-ink-sub">{queueReason(item)}</span>
                            <span>
                                {item.lot_recommendation ? <RecommendationBadge recommendation={item.lot_recommendation} compact /> : <span className="text-xs text-[#9aa0a8]">-</span>}
                            </span>
                            <span>
                                <StatusBadge status={item.status} />
                            </span>
                        </div>
                    )
                })
            )}
        </section>
    )
}