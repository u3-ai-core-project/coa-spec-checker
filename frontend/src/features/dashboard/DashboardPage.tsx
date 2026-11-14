import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/authContext'
import { fetchUsers } from './api'
import FilterBar from './components/FilterBar'
import KpiStrip from './components/KpiStrip'
import { useDashboardSummary } from './hooks/useDashboardSummary'
import { resolveRange, type PeriodKey } from './lib/period'
import type { UserOption } from './types'
import DonutCard from './components/DonutCard'
import { deviationSlices, passFailSlices } from './lib/donut'
import { MATERIALS } from '../upload/lib/upload'
import EditRateCard from './components/EditRateCard'
import { formatPercent } from './lib/format'
import StorageAlert from './components/StorageAlert'

export default function DashboardPage() {
    const { user } = useAuth()
    const isAdmin = user?.role === 'ADMIN'
    const [users, setUsers] = useState<UserOption[]>([])
    const [userId, setUserId] = useState<number | undefined>(undefined)
    const [period, setPeriod] = useState<PeriodKey>('all')
    const [custom, setCustom] = useState({ from: '', to: '' })
    const [material, setMaterial] = useState(MATERIALS[0].code)


    useEffect(() => {
        if (!isAdmin) return
        fetchUsers()
            .then(setUsers)
            .catch(() => setUsers([]))
    }, [isAdmin])

    const range = resolveRange(period, custom)
    const { data, error, reload } = useDashboardSummary({
        userId: isAdmin ? userId : undefined, // 사용자 계정은 user_id를 보내지 않음 (403)
        materialCode: material,
        ...range,
    })

    return (
        <div className="mx-auto flex w-full max-w-[1152px] flex-col gap-4">
            {isAdmin && <StorageAlert />}
            <FilterBar
                isAdmin={isAdmin}
                users={users}
                userId={userId}
                onUserChange={setUserId}
                period={period}
                onPeriodChange={setPeriod}
                custom={custom}
                onCustomChange={setCustom}
                material={material}
                onMaterialChange={setMaterial}
            />

            {error && (
                <div role="alert" className="flex items-center gap-3 rounded-xl border border-line bg-white p-4 text-sm text-[#c0392b]">
                    {error}
                    <button
                        type="button"
                        onClick={reload}
                        className="rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand"
                    >
                        다시 시도
                    </button>
                </div>
            )}

            <KpiStrip data={data} />
            {data && (
                <>
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                        <DonutCard title="합·불 비율" centerLabel="전체" slices={passFailSlices(data)} />
                        <DonutCard title="항목별 이탈 빈도" centerLabel="이탈 합계" slices={deviationSlices(data)} />
                    </div>
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                        <EditRateCard
                            title="협력사별 수정률"
                            headline={
                                data.human_edit_rate != null
                                    ? `전체 수정률 ${formatPercent(data.human_edit_rate)} (문서 기준)`
                                    : undefined
                            }
                            rows={(data.edit_rate_by_supplier ?? []).map((s) => ({
                                name: s.supplier,
                                rate: s.edit_rate,
                                detail: `${s.edited_documents} / ${s.documents}건`,
                            }))}
                        />
                        <EditRateCard
                            title="항목별 수정률"
                            rows={(data.edit_rate_by_item ?? []).map((i) => ({
                                name: i.item_name,
                                rate: i.edit_rate,
                                detail: `${i.edited_items} / ${i.items}개`,
                            }))}
                        />
                    </div>
                </>
            )}
        </div>
    )
}