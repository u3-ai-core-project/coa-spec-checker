import type { ReactNode } from 'react'
import { ChevronDownIcon } from '../../../components/icons'
import { MATERIALS } from '../../upload/lib/upload'
import { PERIOD_OPTIONS, type PeriodKey } from '../lib/period'
import type { UserOption } from '../types'

const SELECT = 'h-full appearance-none bg-transparent pl-1.5 pr-9 text-[13px] font-medium text-ink outline-none'
const DATE = 'h-9 rounded-lg border border-[#cfd4da] bg-white px-3 text-[13px] text-ink outline-none'

function Box({ label, children }: { label: string; children: ReactNode }) {
    return (
        <label className="relative flex h-9 items-center rounded-lg border border-[#cfd4da] bg-white pl-3.5 text-[13px] font-medium text-ink">
            <span>{label}</span>
            {children}
            <ChevronDownIcon className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2" />
        </label>
    )
}

interface Props {
    isAdmin: boolean
    users: UserOption[]
    userId: number | undefined
    onUserChange: (id: number | undefined) => void
    period: PeriodKey
    onPeriodChange: (key: PeriodKey) => void
    custom: { from: string; to: string }
    onCustomChange: (value: { from: string; to: string }) => void
}

export default function FilterBar(props: Props) {
    const { isAdmin, users, userId, onUserChange, period, onPeriodChange, custom, onCustomChange } = props
    return (
        <div className="flex flex-wrap items-center gap-2.5">
            {/* 원자재 필터는 서버(material_code)가 아직 없어서 요청에 보내지 않음. 탄산리튬만 진행 */}
            <Box label="원자재:">
                <select className={SELECT} defaultValue="LI2CO3" aria-label="원자재">
                    {MATERIALS.map((m) => (
                        <option key={m.code} value={m.code} disabled={!m.enabled}>
                            {`${m.name} (${m.formula})`}
                        </option>
                    ))}
                </select>
            </Box>

            {/* 담당자 선택은 관리자만. 사용자가 user_id를 보내면 서버가 403을 줌 */}
            {isAdmin && (
                <Box label="담당자:">
                    <select
                        className={SELECT}
                        value={userId ?? ''}
                        onChange={(e) => onUserChange(e.target.value === '' ? undefined : Number(e.target.value))}
                        aria-label="담당자"
                    >
                        <option value="">전체</option>
                        {users.map((u) => (
                            <option key={u.id} value={u.id}>
                                {u.name}
                            </option>
                        ))}
                    </select>
                </Box>
            )}

            <Box label="기간:">
                <select
                    className={SELECT}
                    value={period}
                    onChange={(e) => onPeriodChange(e.target.value as PeriodKey)}
                    aria-label="기간"
                >
                    {PERIOD_OPTIONS.map((o) => (
                        <option key={o.key} value={o.key}>
                            {o.label}
                        </option>
                    ))}
                </select>
            </Box>

            {period === 'custom' && (
                <div className="flex items-center gap-2 text-[13px] text-ink-sub">
                    <input
                        type="date"
                        value={custom.from}
                        max={custom.to || undefined}
                        onChange={(e) => onCustomChange({ ...custom, from: e.target.value })}
                        className={DATE}
                        aria-label="시작일"
                    />
                    <span>~</span>
                    <input
                        type="date"
                        value={custom.to}
                        min={custom.from || undefined}
                        onChange={(e) => onCustomChange({ ...custom, to: e.target.value })}
                        className={DATE}
                        aria-label="종료일"
                    />
                </div>
            )}
        </div>
    )
}