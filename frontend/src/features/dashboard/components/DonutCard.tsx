import { Cell, Pie, PieChart } from 'recharts'
import type { DonutSlice } from '../lib/donut'
import { formatPercent } from '../lib/format'

interface Props {
    title: string
    centerLabel: string
    slices: DonutSlice[]
}

const EMPTY = [{ name: '없음', value: 1, color: '#eceef1' }]

export default function DonutCard({ title, centerLabel, slices }: Props) {
    const total = slices.reduce((sum, s) => sum + s.value, 0)
    const drawn = total > 0 ? slices : EMPTY // 데이터가 없으면 회색 고리만 보여 줌

    return (
        <section className="rounded-xl border border-line bg-white p-5">
            <h2 className="text-[15px] font-bold text-ink">{title}</h2>
            <div className="mt-3 flex items-center gap-8">
                <div className="relative h-[150px] w-[150px] shrink-0">
                    <PieChart width={150} height={150}>
                        <Pie
                            data={drawn}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={48}
                            outerRadius={75}
                            startAngle={90}
                            endAngle={-270}
                            stroke="none"
                            isAnimationActive={false}
                        >
                            {drawn.map((s) => (
                                <Cell key={s.name} fill={s.color} />
                            ))}
                        </Pie>
                    </PieChart>
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-[22px] font-bold text-ink">{total}건</span>
                        <span className="text-[11px] text-ink-sub">{centerLabel}</span>
                    </div>
                </div>

                <ul className="flex flex-col gap-2.5">
                    {slices.length === 0 ? (
                        <li className="text-xs text-[#9aa0a8]">아직 집계할 데이터가 없습니다.</li>
                    ) : (
                        slices.map((s) => (
                            <li key={s.name} className="flex items-center gap-2 text-sm text-ink">
                                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                                {s.name}
                                <span className="font-bold">{s.value}</span>
                                <span className="text-xs text-ink-sub">
                                    {total > 0 ? formatPercent((s.value / total) * 100) : '—'}
                                </span>
                            </li>
                        ))
                    )}
                </ul>
            </div>
        </section>
    )
}