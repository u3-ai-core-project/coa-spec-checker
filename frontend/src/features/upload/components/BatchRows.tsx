import { Fragment, useState, type ReactNode } from 'react'
import { StatusBadge } from '../../review/shared/components/badges'
import type { BatchAcceptedDocument, BatchQueueItem } from '../batchTypes'
import type { SentBatch } from '../hooks/useBatchUpload'
import { queueReason } from '../lib/batchText'
import { GRID, Mark, Spinner } from './cells'

const extOf = (name: string) => name.split('.').pop()?.toLowerCase() ?? ''

function Row({ name, meta, owner, danger = false, children }: { name: string; meta: string; owner: string; danger?: boolean; children: ReactNode }) {
    return (
        <div className={`${GRID} border-b border-[#eceef1] py-2.5 last:border-b-0 ${danger ? 'bg-[#FFF1F0]' : ''}`}>
            <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-ink">{name}</p>
                <p className="text-[11px] text-[#9aa0a8]">{meta}</p>
            </div>
            <span className="text-[13px] text-ink-sub">{owner}</span>
            {children}
            <span />
        </div>
    )
}

function ErrorText({ text }: { text: string }) {
    return (
        <span className="flex items-center gap-2 text-xs text-[#c0392b]">
            <Mark color="bg-[#ff7875]">!</Mark>
            {text}
        </span>
    )
}

// 실패한 문서 줄: 오류 메시지와 재처리 버튼. 요청 중에는 눌리지 않게 하고, 실패하면 서버 메시지를 보여줌
function FailedStatus({ text, onRetry }: { text: string; onRetry: () => Promise<string | null> }) {
    const [busy, setBusy] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    async function handleClick() {
        setBusy(true)
        setErr(null)
        setErr(await onRetry())
        setBusy(false)
    }

    return (
        <span className="flex items-center gap-3 text-xs text-[#c0392b]">
            <Mark color="bg-[#ff7875]">!</Mark>
            <span className="min-w-0 flex-1">{err ?? text}</span>
            <button
                type="button"
                disabled={busy}
                onClick={handleClick}
                className="shrink-0 whitespace-nowrap rounded-md border border-brand bg-white px-2.5 py-1 text-xs font-bold text-brand disabled:opacity-50"
            >
                {busy ? '요청 중…' : '재처리'}
            </button>
        </span>
    )
}

// 서버가 준 상태 + 문서 정합성 오류로 상태 칸을 정한다 (시안 1-3: 처리 중 / 검수 대상 / 보류 사유 / 격리)
function DocStatus({ doc, item, onRetry }: { doc: BatchAcceptedDocument; item: BatchQueueItem | null; onRetry: () => Promise<string | null> }) {
    const status = item?.status ?? doc.status
    if (status === 'failed') return <FailedStatus text={item?.error_message ?? '문서 처리 오류'} onRetry={onRetry} />
    if (status === 'queued' || status === 'processing') {
        return (
            <span className="flex items-center gap-2 text-xs text-ink-sub">
                <Spinner />
                {status === 'queued' ? '대기' : '처리 중'}
            </span>
        )
    }
    if (item && item.document_issues.length > 0) {
        return (
            <span className="flex items-start gap-2 text-xs text-[#9a6700]">
                <Mark color="bg-[#e3a008]">!</Mark>
                <span>보류 사유 · {queueReason(item)}</span>
            </span>
        )
    }
    if (status === 'extracted') {
        return (
            <span className="flex items-center gap-2 text-xs text-ink">
                <Mark color="bg-brand">✓</Mark>
                검수 대상
            </span>
        )
    }
    return <StatusBadge status={status} />
}

export default function BatchRows({ batches, owner, onRetry }: { batches: SentBatch[]; owner: string; onRetry: (batchId: string, documentId: string) => Promise<string | null> }) {
    return (
        <>
            {batches.map((b) => {
                const items = new Map<string, BatchQueueItem>()
                for (const i of [...(b.detail?.queue ?? []), ...(b.detail?.isolated ?? [])]) items.set(i.document_id, i)
                return (
                    <Fragment key={b.batchId}>
                        {b.csvName && (
                            <Row name={b.csvName} meta="csv · 입고 정보" owner="-">
                                <span className="flex items-center gap-2 text-xs text-ink">
                                    <Mark color="bg-brand">✓</Mark>
                                    {b.receipts}행 인식
                                </span>
                            </Row>
                        )}
                        {b.accepted.map((d) => {
                            const item = items.get(d.document_id) ?? null
                            return (
                                <Row key={d.document_id} name={d.file_name} meta={`${extOf(d.file_name)} · CoA`} owner={owner} danger={(item?.status ?? d.status) === 'failed'}>
                                    <DocStatus doc={d} item={item} onRetry={() => onRetry(b.batchId, d.document_id)} />
                                </Row>
                            )
                        })}
                        {b.rejected.map((r, i) => (
                            <Row key={`${r.file_name}-${i}`} name={r.file_name} meta={extOf(r.file_name)} owner={owner} danger>
                                <ErrorText text={r.message} />
                            </Row>
                        ))}
                    </Fragment>
                )
            })}
        </>
    )
}