import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../api/client'
import { fetchDocument, uploadDocument } from '../api'
import { isSettled } from '../lib/documentStatus'
import { ALLOWED_EXTENSIONS, MAX_FILE_BYTES, MAX_FILES } from '../lib/upload'
import type { DocumentStatus, FinalDecision } from '../types'

export interface ReceiptInfo {
    receivedLotNo: string
    supplier: string
}

export interface QueueItem {
    localId: string
    file: File
    info: ReceiptInfo | null
    phase: 'staged' | 'uploading' | 'uploaded' | 'error'
    documentId: string | null
    status: DocumentStatus | null
    finalDecision: FinalDecision | null
    message: string | null
}

const POLL_MS = 3000

function extensionOf(name: string) {
    return name.split('.').pop()?.toLowerCase() ?? ''
}

function uploadErrorMessage(e: unknown): string {
    if (e instanceof ApiError) {
        if (e.code === 'INVALID_FILE') return '지원하지 않는 형식이거나 손상된 파일입니다.'
        if (e.code === 'UNKNOWN_MATERIAL') return '등록되지 않은 원자재입니다.'
        if (e.code === 'UNKNOWN_SPEC_SET') return '원자재에 맞는 규격 세트가 없습니다.'
        return e.message
    }
    return '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
}

export function useUploadQueue() {
    const [items, setItems] = useState<QueueItem[]>([])
    const itemsRef = useRef<QueueItem[]>([])

    useEffect(() => {
        itemsRef.current = items
    }, [items])

    const patch = useCallback((localId: string, changes: Partial<QueueItem>) => {
        setItems((prev) => prev.map((i) => (i.localId === localId ? { ...i, ...changes } : i)))
    }, [])

    // 고른 파일을 검사해서 목록에 넣고, 넣지 못한 이유를 문장으로 돌려줌
    const addFiles = useCallback((files: File[]): string | null => {
        const notices: string[] = []
        const accepted: QueueItem[] = []
        let room = MAX_FILES - itemsRef.current.length
        for (const file of files) {
            const ext = extensionOf(file.name)
            if (!ALLOWED_EXTENSIONS.includes(ext)) {
                notices.push(`${file.name}: 지원하지 않는 형식입니다.`)
                continue
            }
            if (file.size === 0 || file.size > MAX_FILE_BYTES) {
                notices.push(`${file.name}: 빈 파일이거나 20MB를 넘습니다.`)
                continue
            }
            if (room <= 0) {
                notices.push(`${MAX_FILES}개까지 올릴 수 있습니다.`)
                break
            }
            room -= 1
            accepted.push({
                localId: crypto.randomUUID(),
                file,
                info: null,
                phase: 'staged',
                documentId: null,
                status: null,
                finalDecision: null,
                message: null,
            })
        }
        if (accepted.length > 0) setItems((prev) => [...prev, ...accepted])
        return notices.length > 0 ? [...new Set(notices)].join(' ') : null
    }, [])

    const uploadOne = useCallback(
        async (item: QueueItem, info: ReceiptInfo, materialCode: string) => {
            patch(item.localId, { phase: 'uploading', info, message: null })
            try {
                const result = await uploadDocument({
                    file: item.file,
                    materialCode,
                    supplier: info.supplier,
                    receivedLotNo: info.receivedLotNo,
                })
                patch(item.localId, { phase: 'uploaded', documentId: result.document_id, status: result.status })
            } catch (e) {
                // 서버가 거절한 파일은 다시 해도 같아서 오류로 끝내고, 연결 문제는 다시 시도할 수 있게 남김
                patch(item.localId, { phase: e instanceof ApiError ? 'error' : 'staged', message: uploadErrorMessage(e) })
            }
        },
        [patch],
    )

    // 입고 정보 팝업의 "저장하고 검수 시작"
    const saveInfoAndStart = useCallback(
        async (localId: string, info: ReceiptInfo, materialCode: string) => {
            const item = itemsRef.current.find((i) => i.localId === localId)
            if (item) await uploadOne(item, info, materialCode)
        },
        [uploadOne],
    )

    // 헤더의 "검수 시작": 입고 정보가 있는데 아직 올라가지 않은 파일을 올림
    const startAll = useCallback(
        async (materialCode: string) => {
            const ready = itemsRef.current.filter((i) => i.phase === 'staged' && i.info !== null)
            for (const item of ready) {
                if (item.info) await uploadOne(item, item.info, materialCode)
            }
        },
        [uploadOne],
    )

    const remove = useCallback((localId: string) => {
        setItems((prev) => prev.filter((i) => i.localId !== localId))
    }, [])

    // 처리 중인 문서의 상태를 주기적으로 확인
    useEffect(() => {
        const timer = setInterval(async () => {
            const pending = itemsRef.current.filter(
                (i) => i.phase === 'uploaded' && i.documentId !== null && i.status !== null && !isSettled(i.status),
            )
            if (pending.length === 0) return
            const results = await Promise.allSettled(pending.map((i) => fetchDocument(i.documentId ?? '')))
            results.forEach((r, idx) => {
                if (r.status !== 'fulfilled') return
                patch(pending[idx].localId, {
                    status: r.value.status,
                    finalDecision: r.value.final_decision,
                    message: r.value.error_message,
                })
            })
        }, POLL_MS)
        return () => clearInterval(timer)
    }, [patch])

    return { items, addFiles, saveInfoAndStart, startAll, remove }
}