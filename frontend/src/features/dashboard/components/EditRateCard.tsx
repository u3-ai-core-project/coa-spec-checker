import { formatPercent } from '../lib/format'

export interface EditRateRow {
    name: string
    rate: number // 수정률 0~100
    detail: string
}

interface Props {
    title: string
    headline?: string // 제목 오른쪽 요약 (예: "전체 수정률 20.0%")
    rows: EditRateRow[]
}

const MAX_ROWS = 5 // 서버가 수정률 높은 순으로 보내므로 위에서 5개만 보여 줌

export default function EditRateCard({ title, headline, rows }: Props) {
    const shown = rows.slice(0, MAX_ROWS)

    return (
        <section className="rounded-xl border border-line bg-white p-5">
            <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-[15px] font-bold text-ink">{title}</h2>
                {headline && <span className="text-xs text-ink-sub">{headline}</span>}
            </div>

            <ul className="mt-4 flex flex-col gap-3">
                {shown.length === 0 ? (
                    <li className="text-xs text-[#9aa0a8]">아직 집계할 데이터가 없습니다.</li>
                ) : (
                    shown.map((r) => (
                        <li key={r.name} className="flex items-center gap-3 text-sm text-ink">
                            <span className="w-24 shrink-0 truncate" title={r.name}>{r.name}</span>
                            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#eceef1]">
                                <div
                                    className="h-full bg-[#2b4fcb]"
                                    style={{ width: `${Math.min(100, Math.max(0, r.rate))}%` }}
                                />
                            </div>
                            <span className="w-14 shrink-0 text-right font-bold">{formatPercent(r.rate)}</span>
                            <span className="w-16 shrink-0 text-right text-xs text-ink-sub">{r.detail}</span>
                        </li>
                    ))
                )}
            </ul>
        </section>
    )
}