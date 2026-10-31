import { useCallback, useState } from 'react'
import type { DocumentListItem } from '../review/shared/api/types'
import { downloadReport } from './api'
import FilterBar from './components/FilterBar'
import ReportTable, { type RowState } from './components/ReportTable'
import Toast, { type ToastData } from './components/Toast'
import { useReports } from './hooks/useReports'
import { DEFAULT_FILTERS, filterReports, type ReportFilters } from './lib/filters'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const nameOf = (item: DocumentListItem) => item.lot_no ?? item.file_name

export default function ReportsPage() {
    const { items, reasons, loading, error, reload } = useReports()
    const [filters, setFilters] = useState<ReportFilters>(DEFAULT_FILTERS)
    const [selected, setSelected] = useState<Set<string>>(new Set())
    const [rowStates, setRowStates] = useState<Record<string, RowState>>({})
    const [toast, setToast] = useState<ToastData | null>(null)
    const closeToast = useCallback(() => setToast(null), [])

    const visible = filterReports(items, filters)
    const selectedVisible = visible.filter((item) => selected.has(item.document_id))
    const busy = Object.values(rowStates).includes('busy')

    function toggle(id: string) {
        setSelected((prev) => {
            const next = new Set(prev)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
        })
    }

    function setRowState(id: string, state: RowState | null) {
        setRowStates((prev) => {
            const next = { ...prev }
            if (state === null) delete next[id]
            else next[id] = state
            return next
        })
    }

    // 문서 1건의 리포트를 받음. 성공하면 true
    async function fetchOne(item: DocumentListItem): Promise<boolean> {
        setRowState(item.document_id, 'busy')
        try {
            await downloadReport(item.document_id)
            setRowState(item.document_id, null)
            return true
        } catch {
            setRowState(item.document_id, 'failed')
            return false
        }
    }

    async function handleRow(item: DocumentListItem) {
        const retry = rowStates[item.document_id] === 'failed'
        const ok = await fetchOne(item)
        setToast(
            ok
                ? { type: 'success', message: retry ? `${nameOf(item)} 리포트가 다시 생성되었습니다.` : `${nameOf(item)} 리포트 1건을 다운로드했습니다.` }
                : { type: 'error', message: `${nameOf(item)} 리포트 생성에 실패했습니다. '재생성'으로 다시 시도해 주세요.` },
        )
    }

    // 명세에 일괄 다운로드 API가 없어서 선택한 문서를 차례로 하나씩 받음
    async function handleBulk() {
        const targets = selectedVisible
        let done = 0
        let failed = 0
        for (const item of targets) {
            if (await fetchOne(item)) done += 1
            else failed += 1
            await sleep(300)
        }
        if (failed === 0) {
            setToast({
                type: 'success',
                message: targets.length === 1 ? `${nameOf(targets[0])} 리포트 1건을 다운로드했습니다.` : `리포트 ${done}건을 다운로드했습니다.`,
            })
        } else {
            setToast({
                type: 'error',
                message: `리포트 ${done}건을 다운로드했고 ${failed}건은 실패했습니다. 실패한 행의 '재생성'을 눌러 주세요.`,
            })
        }
    }

    return (
        <div className="mx-auto flex w-full max-w-[1152px] flex-col gap-4">
            <div className="rounded-xl border border-line bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <FilterBar filters={filters} onChange={setFilters} />
                    <div className="flex items-center gap-3">
                        <span className={`text-xs ${selectedVisible.length > 0 ? 'font-bold text-ink' : 'text-ink-sub'}`}>
                            {selectedVisible.length}건 선택됨
                        </span>
                        <button
                            type="button"
                            disabled={selectedVisible.length === 0 || busy}
                            onClick={() => void handleBulk()}
                            className="rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white disabled:bg-[#eceef1] disabled:text-[#9aa0a8]"
                        >
                            선택 항목 일괄 다운로드
                        </button>
                    </div>
                </div>

                {error ? (
                    <div role="alert" className="mt-3 flex items-center gap-3 text-sm text-[#c0392b]">
                        {error}
                        <button
                            type="button"
                            onClick={reload}
                            className="rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand"
                        >
                            다시 시도
                        </button>
                    </div>
                ) : loading ? (
                    <p className="py-10 text-center text-[13px] text-ink-sub">불러오는 중…</p>
                ) : visible.length === 0 ? (
                    <p className="py-10 text-center text-[13px] text-ink-sub">
                        {items.length === 0 ? '처분이 완료된 문서가 없습니다.' : '조건에 맞는 리포트가 없습니다.'}
                    </p>
                ) : (
                    <ReportTable
                        items={visible}
                        reasons={reasons}
                        selected={selected}
                        rowStates={rowStates}
                        onToggle={toggle}
                        onDownload={(item) => void handleRow(item)}
                    />
                )}

                <p className="mt-3 text-[11px] text-ink-sub">*처분 일시 최신순으로 정렬됩니다.</p>
            </div>

            <Toast toast={toast} onClose={closeToast} />
        </div>
    )
}