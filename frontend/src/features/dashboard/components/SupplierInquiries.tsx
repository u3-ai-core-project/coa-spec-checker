import { useState } from 'react'
import type { FollowUpsResponse } from '../../review/shared/api/types'
import type { BatchQueueItem } from '../../upload/batchTypes'
import { needsFollowUp, useFollowUps } from '../hooks/useFollowUps'

interface Row {
    item: BatchQueueItem
    res: FollowUpsResponse | null | undefined // undefined = 불러오는 중, null = 실패
}

function requestText(res: FollowUpsResponse | null | undefined): string {
    if (res === undefined) return '불러오는 중…'
    if (res === null) return '요청 내용을 불러오지 못했습니다'
    const lines = res.supplier_lines
    if (lines.length === 0) return '내부 확인 항목만 있음'
    const shown = lines
        .slice(0, 2)
        .map((l) => `${l.target} ${l.label}`)
        .join(' · ')
    return lines.length > 2 ? `${shown} 외 ${lines.length - 2}건` : shown
}

// 같은 공급사의 메일 1통(묶음 초안)이 있으면 그것을, 없으면 로트 초안 사용
function draftOf(rows: Row[]) {
    for (const r of rows) if (r.res?.combined_draft) return r.res.combined_draft
    for (const r of rows) if (r.res?.draft) return r.res.draft
    return null
}

export default function SupplierInquiries({ items }: { items: BatchQueueItem[] }) {
    const { map, loading } = useFollowUps(items)
    const [copied, setCopied] = useState<string | null>(null)

    const groups = new Map<string, Row[]>()
    for (const item of items.filter(needsFollowUp)) {
        const name = item.supplier ?? '공급사 미상'
        groups.set(name, [...(groups.get(name) ?? []), { item, res: map[item.document_id] }])
    }
    const total = [...groups.values()].reduce((n, rows) => n + rows.length, 0)
    const merged = [...groups.values()].some((rows) => rows.some((r) => r.res?.combined_draft))

    async function copy(name: string, rows: Row[]) {
        const draft = draftOf(rows)
        if (!draft) return
        try {
            await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.body}`)
            setCopied(name)
            setTimeout(() => setCopied(null), 2000)
        } catch {
            setCopied(null)
        }
    }

    return (
        <section className="overflow-hidden rounded-xl border border-line bg-white">
            <div className="flex items-center justify-between px-5 py-4">
                <h2 className="text-[15px] font-bold text-ink">공급사별 문의 묶음</h2>
                <span className="text-xs text-ink-sub">
                    {total}건 · {groups.size}개사
                </span>
            </div>

            {groups.size === 0 ? (
                <p className="border-t border-line px-5 py-5 text-xs text-[#9aa0a8]">문의가 필요한 로트가 없습니다.</p>
            ) : (
                [...groups.entries()].map(([name, rows]) => {
                    const draft = draftOf(rows)
                    return (
                        <div key={name} className="flex flex-col gap-2 border-t border-line px-5 py-4">
                            <div className="flex items-center gap-2">
                                <span className="text-sm font-bold text-ink">{name}</span>
                                <span className="text-xs text-ink-sub">{rows.length}건</span>
                                <button
                                    type="button"
                                    disabled={!draft}
                                    onClick={() => void copy(name, rows)}
                                    className="ml-auto rounded-md border border-[#cfd4da] bg-white px-2.5 py-1 text-xs font-bold text-ink disabled:text-[#9aa0a8]"
                                >
                                    {copied === name ? '복사됨' : '문의 초안 복사'}
                                </button>
                            </div>
                            {rows.map(({ item, res }) => {
                                const done = item.status === 'approved'
                                return (
                                    <p key={item.document_id} className={`flex gap-3 text-xs ${done ? 'text-[#9aa0a8]' : 'text-ink-sub'}`}>
                                        <span className={`w-[72px] shrink-0 font-medium ${done ? '' : 'text-ink'}`}>{item.lot_no ?? item.received_lot_no ?? '-'}</span>
                                        <span>
                                            {requestText(res)}
                                            {done && ' (처분 완료 건)'}
                                        </span>
                                    </p>
                                )
                            })}
                        </div>
                    )
                })
            )}

            {(loading || merged) && (
                <p className="border-t border-line px-5 py-3 text-[11px] text-[#9aa0a8]">
                    {loading ? '문의 초안을 불러오는 중입니다.' : '같은 공급사의 다른 열린 요청도 한 통의 메일로 함께 묶일 수 있습니다.'}
                </p>
            )}
        </section>
    )
}