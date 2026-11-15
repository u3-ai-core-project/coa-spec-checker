import { apiFetch } from '../../api/client'
import type { DocumentDetail, DocumentStatus, UploadResult } from './types'

export interface UploadParams {
    file: File
    materialCode: string
    supplier?: string
    receivedLotNo?: string
    confirmDuplicate?: boolean // 같은 파일 경고를 보고 "그래도 접수"를 눌렀을 때
}

// 파일 1개씩 업로드하고 여러 파일은 화면에서 한 개씩 호출
export function uploadDocument({ file, materialCode, supplier, receivedLotNo, confirmDuplicate }: UploadParams) {
    const form = new FormData()
    form.append('file', file)
    form.append('material_code', materialCode)
    if (supplier) form.append('supplier', supplier)
    if (receivedLotNo) form.append('received_lot_no', receivedLotNo)
    if (confirmDuplicate) form.append('confirm_duplicate', 'true')
    return apiFetch<UploadResult>('/documents', { method: 'POST', body: form })
}

// 처리 상태 확인용 
export function fetchDocument(documentId: string) {
    return apiFetch<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}`)
}

// 실패한 문서 다시 처리. 성공하면 서버 상태가 queued로 돌아감
export function retryDocument(documentId: string) {
    return apiFetch<{ document_id: string; file_name: string; status: DocumentStatus }>(
        `/documents/${encodeURIComponent(documentId)}/retry`,
        { method: 'POST' },
    )
}