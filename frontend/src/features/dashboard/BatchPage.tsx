import type { ReactNode } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useAuth } from '../../auth/authContext'
import { MATERIALS } from '../upload/lib/upload'
import BatchKpi from './components/BatchKpi'
import BatchQueue from './components/BatchQueue'
import UnmatchedReceipts from './components/UnmatchedReceipts'
import { useBatch } from './hooks/useBatch'
import { allItems, formatKst } from './lib/batchView'

function Pill({ children }: { children: ReactNode }) {
    return <span className="flex h-9 items-center rounded-lg border border-[#cfd4da] bg-white px-3.5 text-[13px] font-medium text-ink">{children}</span>
}

export default function BatchPage() {
    const { user } = useAuth()
    const isAdmin = user?.role === 'ADMIN'
    const { batchId = '' } = useParams()
    const { data, error, loading, reload } = useBatch(isAdmin ? batchId : '') // 관리자가 아니면 요청하지 않음

    if (!isAdmin) return <Navigate to="/dashboard" replace />

    const material = data ? MATERIALS.find((m) => m.code === data.material_code) : undefined
    return (
        <div className="mx-auto flex w-full max-w-[1152px] flex-col gap-4">
            {data && (
                <div className="flex flex-wrap gap-2.5">
                    <Pill>원자재: {material ? `${material.name} (${material.formula})` : data.material_code}</Pill>
                    <Pill>접수자: {data.created_by}</Pill>
                    <Pill>접수 일시: {formatKst(data.created_at)}</Pill>
                </div>
            )}

            {error && (
                <div role="alert" className="flex items-center gap-3 rounded-xl border border-line bg-white p-4 text-sm text-[#c0392b]">
                    {error}
                    <button type="button" onClick={reload} className="rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand">
                        다시 시도
                    </button>
                </div>
            )}
            {loading && <p className="text-sm text-ink-sub">배치 현황을 불러오는 중…</p>}

            {data && (
                <>
                    <BatchKpi summary={data.summary} />
                    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_392px]">
                        <BatchQueue items={allItems(data)} />
                        <div className="flex flex-col gap-4">
                            {/* 공급사별 문의 묶음 카드는 문의 초안 요청 함수를 확인한 뒤 여기에 추가 */}
                            <UnmatchedReceipts receipts={data.unmatched_receipts} />
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}