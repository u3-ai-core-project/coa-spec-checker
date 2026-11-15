import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/authContext'
import { CloseIcon, UploadIcon } from '../../components/icons'
import MaterialSelect from './components/MaterialSelect'
import ReceiptDialog from './components/ReceiptDialog'
import { DECISION_LABEL, STATUS_LABEL } from './lib/documentStatus'
import { MATERIALS, MAX_FILES } from './lib/upload'
import { useUploadQueue, type QueueItem } from './hooks/useUploadQueue'
import { GRID, Mark, Spinner } from './components/cells'
import BatchRows from './components/BatchRows'
import { useBatchUpload } from './hooks/useBatchUpload'
import { splitSelection } from './lib/selection'
import { failureHint } from './lib/failure'
import { useStorageStatus } from './storage'

function fileMeta(file: File) {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
    const size =
        file.size < 1024 * 1024
            ? `${Math.max(1, Math.round(file.size / 1024))}KB`
            : `${(file.size / 1024 / 1024).toFixed(1)}MB`
    return `${ext} · ${size}`
}

function StatusCell({ item, onOpenDialog, onRetry, onReprocess, onViewDuplicate, onConfirmDuplicate }: {
    item: QueueItem; onOpenDialog: () => void; onRetry: () => void; onReprocess: () => void
    onViewDuplicate: (documentId: string) => void; onConfirmDuplicate: () => void
}) {
    if (item.phase === 'staged' && item.info === null) {
        return (
            <div className="flex items-center gap-2 text-xs text-[#9a6700]">
                <Mark color="bg-[#e3a008]">!</Mark>
                입고 정보 필요
                <button
                    type="button"
                    onClick={onOpenDialog}
                    className="rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand"
                >
                    입고 정보 입력
                </button>
            </div>
        )
    }
    if (item.phase === 'staged' && item.duplicates && item.duplicates.length > 0) {
        const dup = item.duplicates[0]
        return (
            <span className="flex flex-wrap items-center gap-2 text-xs text-[#9a6700]">
                <Mark color="bg-[#e3a008]">!</Mark>
                <span className="min-w-0 flex-1">
                    같은 파일이 이미 있습니다
                    <span className="block text-[11px] text-ink-sub">
                        {dup.file_name} ({STATUS_LABEL[dup.status]})
                        {item.duplicates.length > 1 ? ` 외 ${item.duplicates.length - 1}건` : ''}
                    </span>
                </span>
                <button type="button" onClick={() => onViewDuplicate(dup.document_id)}
                    className="shrink-0 whitespace-nowrap rounded-md border border-line bg-white px-2.5 py-1 text-xs font-bold text-ink">
                    보기
                </button>
                <button type="button" onClick={onConfirmDuplicate}
                    className="shrink-0 whitespace-nowrap rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand">
                    그래도 접수
                </button>
            </span>
        )
    }
    if (item.phase === 'staged') {
        return (
            <span className={`text-xs ${item.message ? 'text-[#c0392b]' : 'text-ink-sub'}`}>
                {item.message ?? '시작 전'}
                <button
                    type="button"
                    onClick={onRetry}
                    className="rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand"
                >
                    다시 시도
                </button>
            </span>
        )
    }
    if (item.phase === 'uploading') {
        return (
            <span className="flex items-center gap-2 text-xs text-ink-sub">
                <Spinner />
                업로드 중
            </span>
        )
    }
    if (item.phase === 'error' || item.status === 'failed') {
        return (
            <span className="flex items-center gap-3 text-xs text-[#c0392b]">
                <Mark color="bg-[#ff7875]">!</Mark>
                <span className="min-w-0 flex-1">
                    {item.message ?? STATUS_LABEL.failed}
                    {failureHint(item.failedStage, item.errorKind, item.attemptCount) && (
                        <span className="block text-[11px] text-ink-sub">
                            {failureHint(item.failedStage, item.errorKind, item.attemptCount)}
                        </span>
                    )}
                </span>
                {item.phase !== 'error' && item.documentId && (
                    <button
                        type="button"
                        onClick={onReprocess}
                        className="shrink-0 whitespace-nowrap rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand"
                    >
                        재처리
                    </button>
                )}
            </span>
        )
    }
    const status = item.status ?? 'queued'
    if (status === 'extracted') {
        return (
            <span className="flex items-center gap-2 text-xs text-ink">
                <Mark color="bg-brand">✓</Mark>
                검수 대상
            </span>
        )
    }
    if (status === 'queued' || status === 'processing') {
        return (
            <span className="flex items-center gap-2 text-xs text-ink-sub">
                <Spinner />
                {STATUS_LABEL[status]}
            </span>
        )
    }
    if (status === 'approved') {
        return (
            <span className="text-xs text-ink-sub">
                {STATUS_LABEL.approved}
                {item.finalDecision ? ` (${DECISION_LABEL[item.finalDecision]})` : ''}
            </span>
        )
    }
    return (
        <span className={`text-xs ${status === 'on_hold' ? 'text-[#9a6700]' : 'text-ink-sub'}`}>
            {STATUS_LABEL[status]}
        </span>
    )
}

export default function UploadPage() {
    const { user } = useAuth()
    const queue = useUploadQueue()
    const batch = useBatchUpload()
    const storage = useStorageStatus()
    const [materialCode, setMaterialCode] = useState(MATERIALS[0].code)
    const [notice, setNotice] = useState<string | null>(null)
    const [dragging, setDragging] = useState(false)
    const [dialogId, setDialogId] = useState<string | null>(null)
    const inputRef = useRef<HTMLInputElement>(null)
    const navigate = useNavigate()
    const singleId = queue.items.find((i) => i.phase === 'uploaded' && i.status === 'extracted')?.documentId
    const batchDocId = batch.batches.flatMap((b) => b.detail?.queue ?? []).find((i) => i.status === 'extracted')?.document_id
    const readyId = singleId ?? batchDocId
    const batchCount = batch.batches.reduce((n, b) => n + b.accepted.length + b.rejected.length + (b.csvName ? 1 : 0), 0)
    const isolatedCount = batch.batches.reduce((n, b) => n + b.rejected.length + (b.detail?.isolated.length ?? 0), 0)
    const total = queue.items.length + batchCount

    const dialogItem = queue.items.find((i) => i.localId === dialogId)

    async function handleSelect(files: File[]) {
        if (storage?.level === 'block') {
            setNotice('저장 공간이 부족해 새 업로드를 받을 수 없습니다. 관리자에게 문의해 주세요.')
            return
        }
        const { coa, csv, other } = splitSelection(files)
        const notes: string[] = []
        if (other.length > 0) notes.push(`${other.length}개 파일은 지원하지 않는 형식이라 제외했습니다.`)
        if (csv.length > 1) {
            setNotice('입고 정보 CSV는 1개만 선택할 수 있습니다.')
            return
        }
        if (csv.length === 1 && coa.length === 0) {
            setNotice('입고 정보 CSV는 CoA 파일과 함께 선택해 주세요.')
            return
        }
        if (coa.length > MAX_FILES) {
            setNotice(`한 번에 ${MAX_FILES}개까지 선택할 수 있습니다.`)
            return
        }
        if (coa.length >= 2 || csv.length === 1) {
            const err = await batch.submit(coa, csv[0], materialCode) // 일괄 접수
            if (err) notes.push(err)
        } else if (coa.length === 1) {
            const msg = queue.addFiles(coa) // 입고 정보 팝업
            if (msg) notes.push(msg)
        }
        setNotice(notes.length > 0 ? notes.join(' ') : null)
    }

    function onDrop(e: DragEvent<HTMLDivElement>) {
        e.preventDefault()
        setDragging(false)
        void handleSelect(Array.from(e.dataTransfer.files))
    }

    function onPick(e: ChangeEvent<HTMLInputElement>) {
        void handleSelect(Array.from(e.target.files ?? []))
        e.target.value = ''
    }

    return (
        <div className="mx-auto flex w-full max-w-[900px] flex-col gap-4">
            <MaterialSelect value={materialCode} onChange={setMaterialCode} />
            {storage && storage.level !== 'ok' && (
                <p role="status" className={`rounded-lg px-4 py-3 text-xs ${storage.level === 'block' ? 'bg-[#FFF1F0] text-[#c0392b]' : 'bg-[#FFF8E6] text-[#9a6700]'}`}>
                    {storage.level === 'block'
                        ? (storage.reason === 'disk'
                            ? '서버 디스크의 남은 공간이 부족해 새 업로드를 받을 수 없습니다. 관리자에게 문의하세요.'
                            : '저장 공간이 부족해 새 업로드를 받을 수 없습니다. 관리자에게 문의하세요.')
                        : `저장 공간이 거의 찼습니다 (사용 ${Math.round(storage.used_percent)}%). 관리자에게 정리를 요청해 주세요.`}
                </p>
            )}
            <div
                onDragOver={(e) => {
                    e.preventDefault()
                    setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex h-[196px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed ${dragging ? 'border-brand bg-brand-soft' : 'border-[#cfd4da] bg-white'
                    }`}
            >
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-soft text-brand">
                    <UploadIcon />
                </span>
                <p className="text-sm text-ink">검수할 CoA 파일을 끌어다 놓거나, 파일 선택 버튼을 눌러주세요.</p>
                <p className="text-xs text-ink-sub">지원 형식: PDF, PNG, JPG, CSV</p>
                <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    className="mt-1 flex h-10 items-center gap-1.5 rounded-lg bg-brand px-5 text-sm font-bold text-white"
                >
                    <UploadIcon />
                    파일 선택
                </button>
                <input ref={inputRef} type="file" multiple accept=".pdf,.png,.jpg,.csv" className="hidden" onChange={onPick} />
                {batch.sending && <p className="text-xs text-ink-sub">일괄 접수 중…</p>}
            </div>

            {
                notice && (
                    <p role="alert" className="text-xs text-[#c0392b]">
                        {notice}
                    </p>
                )
            }

            <div className="overflow-hidden rounded-xl border border-line bg-white">
                <div className="flex h-16 items-center justify-between px-5">
                    <p className="text-[15px] font-bold text-ink">
                        <span className="text-brand">{total}개</span>
                        {isolatedCount > 0 && <span className="text-xs text-[#c0392b]"> (격리 {isolatedCount}건 포함)</span>} / {MAX_FILES}개
                    </p>
                    <button
                        type="button"
                        disabled={!readyId}
                        onClick={() => { if (readyId) navigate(`/inspection/${readyId}`) }}
                        className="rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white disabled:bg-[#eceef1] disabled:text-[#9aa0a8]"
                    >
                        검수 시작
                    </button>
                </div>

                <div className={`${GRID} border-y border-line bg-[#f7f8fa] py-2.5 text-xs font-bold text-ink-sub`}>
                    <span>파일명</span>
                    <span>담당자</span>
                    <span>상태</span>
                    <span />
                </div>

                {queue.items.length === 0 && batch.batches.length === 0 ? (
                    <div className="flex flex-col items-center gap-1 py-10">
                        <p className="text-[13px] text-ink">아직 업로드한 파일이 없습니다.</p>
                        <p className="text-xs text-[#9aa0a8]">위 영역에 CoA 파일을 끌어다 놓거나 파일 선택 버튼을 눌러주세요.</p>
                    </div>
                ) : (
                    <>
                        {queue.items.map((item) => (
                            <div
                                key={item.localId}
                                className={`${GRID} border-b border-[#eceef1] py-2.5 last:border-b-0 ${item.phase === 'error' || item.status === 'failed' ? 'bg-[#FFF1F0]' : ''
                                    }`}
                            >
                                <div className="min-w-0">
                                    <p className="truncate text-[13px] font-medium text-ink">{item.file.name}</p>
                                    <p className="text-[11px] text-[#9aa0a8]">{fileMeta(item.file)}</p>
                                </div>
                                <span className="text-[13px] text-ink-sub">{user?.name}</span>
                                <StatusCell item={item} onReprocess={() => void queue.retry(item.localId)} onOpenDialog={() => setDialogId(item.localId)} onRetry={() => { if (item.info) void queue.saveInfoAndStart(item.localId, item.info, materialCode) }} onViewDuplicate={(id) => navigate(`/inspection/${id}`)} onConfirmDuplicate={() => void queue.confirmDuplicate(item.localId, materialCode)} />
                                <div className="flex justify-end">
                                    <button
                                        type="button"
                                        onClick={() => queue.remove(item.localId)}
                                        aria-label={`${item.file.name} 삭제`}
                                        className="text-[#9aa0a8] hover:text-ink"
                                    >
                                        <CloseIcon />
                                    </button>
                                </div>
                            </div>
                        ))}
                        <BatchRows
                            batches={batch.batches}
                            owner={user?.name ?? ''}
                            onRetry={batch.retry}
                            onViewDuplicate={(id) => navigate(`/inspection/${id}`)}
                            onConfirmDuplicate={(batchId, fileName) => batch.confirmDuplicate(batchId, fileName, materialCode)}
                        />
                    </>
                )}
            </div>

            {
                dialogItem && (
                    <ReceiptDialog
                        key={dialogItem.localId}
                        fileName={dialogItem.file.name}
                        onCancel={() => setDialogId(null)}
                        onSubmit={(info) => {
                            setDialogId(null)
                            void queue.saveInfoAndStart(dialogItem.localId, info, materialCode)
                        }}
                    />
                )
            }
        </div >
    )
}