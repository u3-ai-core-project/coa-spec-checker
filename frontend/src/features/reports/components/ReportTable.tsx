import { formatKst } from '../../dashboard/lib/batchView'
import type { DocumentListItem } from '../../review/shared/api/types'
import { DispositionBadge, RecommendationBadge } from '../../review/shared/components/badges'
import type { Decision } from '../lib/filters'

export type RowState = 'busy' | 'failed'


const REASON_COLOR: Record<Decision, string> = {
    accept: 'text-ink-sub',
    conditional_accept: 'text-[#9a6700]',
    reject: 'text-[#c0392b]',
}

const TH = 'px-3 py-2.5 text-xs font-bold text-ink-sub'
const EMPTY = <span className="text-xs text-[#9aa0a8]">-</span>

interface Props {
    items: DocumentListItem[]
    reasons: Record<string, string>
    selected: Set<string>
    rowStates: Record<string, RowState>
    onToggle: (id: string) => void
    onDownload: (item: DocumentListItem) => void
}

export default function ReportTable({ items, reasons, selected, rowStates, onToggle, onDownload }: Props) {
    return (
        <div className="mt-3 overflow-hidden rounded-lg border border-line">
            <table className="w-full">
                <thead className="bg-[#f7f8fa]">
                    <tr>
                        <th className="w-10 px-3 py-2.5" />
                        <th className={`${TH} text-left`}>로트</th>
                        <th className={`${TH} text-left`}>협력사</th>
                        <th className={`${TH} text-left`}>AI 권고</th>
                        <th className={`${TH} text-left`}>담당자 처분 결과</th>
                        <th className={`${TH} text-left`}>처분 일시</th>
                        <th className={`${TH} text-left`}>처분자</th>
                        <th className={`${TH} w-[120px] text-left`}>다운로드</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((item) => {
                        const id = item.document_id
                        const state = rowStates[id]
                        const reason = reasons[id]
                        return (
                            <tr key={id} className="border-t border-line">
                                <td className="w-10 px-3 py-3">
                                    <input
                                        type="checkbox"
                                        checked={selected.has(id)}
                                        onChange={() => onToggle(id)}
                                        aria-label={`${item.lot_no ?? item.file_name} 선택`}
                                        className="h-4 w-4 accent-brand"
                                    />
                                </td>
                                <td className="px-3 py-3 text-[13px] font-medium text-ink">{item.lot_no ?? '-'}</td>
                                <td className="px-3 py-3 text-[13px] text-ink">{item.supplier}</td>
                                <td className="px-3 py-3">
                                    {item.lot_recommendation ? (
                                        <RecommendationBadge recommendation={item.lot_recommendation} compact />
                                    ) : (
                                        EMPTY
                                    )}
                                </td>
                                <td className="px-3 py-3">
                                    {item.final_decision ? (
                                        <div className="flex items-center gap-2">
                                            <DispositionBadge disposition={item.final_decision} compact />
                                            {reason && (
                                                <span
                                                    className={`max-w-[260px] truncate text-[11px] ${REASON_COLOR[item.final_decision]}`}
                                                    title={reason}
                                                >
                                                    {reason}
                                                </span>
                                            )}
                                        </div>
                                    ) : (
                                        EMPTY
                                    )}
                                </td>
                                <td className="px-3 py-3 text-xs tabular-nums text-ink">
                                    {item.approved_at ? formatKst(item.approved_at) : '-'}
                                </td>
                                <td className="px-3 py-3 text-[13px] text-ink">{item.approved_by ?? '-'}</td>
                                <td className="px-3 py-3 text-left">
                                    {state === 'failed' ? (
                                        <button
                                            type="button"
                                            onClick={() => onDownload(item)}
                                            className="rounded-md border border-[#c0392b] bg-white px-3 py-1.5 text-xs font-bold text-[#c0392b]"
                                        >
                                            ↻ 재생성
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            disabled={state === 'busy'}
                                            onClick={() => onDownload(item)}
                                            className="rounded-md bg-brand px-3 py-1.5 text-xs font-bold text-white disabled:bg-[#eceef1] disabled:text-[#9aa0a8]"
                                        >
                                            {state === 'busy' ? '생성 중…' : '다운로드'}
                                        </button>
                                    )}
                                </td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}