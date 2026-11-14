import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../api/client'
import { createBatch, fetchBatch } from '../batchApi'
import { retryDocument } from '../api'
import type { BatchAcceptedDocument, BatchDetail, BatchRejectedFile } from '../batchTypes'

export interface SentBatch {
    batchId: string
    csvName: string | null
    receipts: number // 입고 CSV 행 수
    accepted: BatchAcceptedDocument[]
    rejected: BatchRejectedFile[]
    detail: BatchDetail | null // 상태를 한 번 불러오면 채워진다
}
// 서버가 거절한 파일에 원본 File을 붙여 둔다 ("그래도 접수"로 다시 보낼 때 필요)
function attachFiles(rejected: BatchRejectedFile[], files: File[]): BatchRejectedFile[] {
    return rejected.map((r) => ({ ...r, file: files.find((f) => f.name === r.file_name) }))
}

const POLL_MS = 3000

export function useBatchUpload() {
    const [batches, setBatches] = useState<SentBatch[]>([])
    const [sending, setSending] = useState(false)
    const ref = useRef<SentBatch[]>([])

    useEffect(() => {
        ref.current = batches
    }, [batches])

    // 일괄 접수. 실패하면 화면에 보일 문구를 돌려주고, 성공하면 null
    const submit = useCallback(async (files: File[], csv: File | undefined, materialCode: string) => {
        setSending(true)
        try {
            const res = await createBatch({ files, receipts: csv, materialCode })
            setBatches((prev) => [
                ...prev,
                {
                    batchId: res.batch_id,
                    csvName: csv?.name ?? null,
                    receipts: res.receipts,
                    accepted: res.documents,
                    rejected: attachFiles(res.rejected, files),
                    detail: null,
                },
            ])
            return null
        } catch (e) {
            return e instanceof ApiError ? e.message : '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
        } finally {
            setSending(false)
        }
    }, [])

    // 실패한 문서 다시 처리. 성공하면 null, 실패하면 화면에 보일 문구를 돌려줌
    const retry = useCallback(async (batchId: string, documentId: string) => {
        try {
            await retryDocument(documentId)
            const detail = await fetchBatch(batchId)
            setBatches((prev) => prev.map((b) => (b.batchId === batchId ? { ...b, detail } : b)))
            return null
        } catch (e) {
            return e instanceof ApiError ? e.message : '다시 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
        }
    }, [])

    // 같은 파일 경고에서 "그래도 접수": 그 파일만 새 묶음으로 접수한다 (입고 CSV 없이)
    const confirmDuplicate = useCallback(async (batchId: string, fileName: string, materialCode: string) => {
        const file = ref.current.find((b) => b.batchId === batchId)?.rejected.find((r) => r.file_name === fileName)?.file
        if (!file) return '파일을 찾지 못했습니다. 다시 선택해 주세요.'
        try {
            const res = await createBatch({ files: [file], materialCode, confirmDuplicate: true })
            setBatches((prev) => [
                ...prev.map((b) => (b.batchId === batchId ? { ...b, rejected: b.rejected.filter((r) => r.file_name !== fileName) } : b)),
                {
                    batchId: res.batch_id,
                    csvName: null,
                    receipts: res.receipts,
                    accepted: res.documents,
                    rejected: attachFiles(res.rejected, [file]),
                    detail: null,
                },
            ])
            return null
        } catch (e) {
            return e instanceof ApiError ? e.message : '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
        }
    }, [])

    // 처리 중인 문서가 남은 배치만 다시 불러온다
    useEffect(() => {
        const timer = setInterval(async () => {
            const pending = ref.current.filter(
                (b) => b.accepted.length > 0 && (b.detail === null || b.detail.summary.processing > 0),
            )
            if (pending.length === 0) return
            const results = await Promise.allSettled(pending.map((b) => fetchBatch(b.batchId)))
            setBatches((prev) =>
                prev.map((b) => {
                    const i = pending.findIndex((p) => p.batchId === b.batchId)
                    if (i < 0) return b
                    const r = results[i]
                    return r.status === 'fulfilled' ? { ...b, detail: r.value } : b
                }),
            )
        }, POLL_MS)
        return () => clearInterval(timer)
    }, [])

    return { batches, sending, submit, retry, confirmDuplicate }
}