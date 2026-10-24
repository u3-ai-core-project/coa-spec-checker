import { apiFetch } from '../../api/client'
import type { DocumentDetail, UploadResult } from './types'

export interface UploadParams {
    file: File
    materialCode: string
    supplier?: string
    receivedLotNo?: string
}

// 파일 1개씩 업로드하고 여러 파일은 화면에서 한 개씩 호출
export function uploadDocument({ file, materialCode, supplier, receivedLotNo }: UploadParams) {
    const form = new FormData()
    form.append('file', file)
    form.append('material_code', materialCode)
    if (supplier) form.append('supplier', supplier)
    if (receivedLotNo) form.append('received_lot_no', receivedLotNo)
    return apiFetch<UploadResult>('/documents', { method: 'POST', body: form })
}

// 처리 상태 확인용 
export function fetchDocument(documentId: string) {
    return apiFetch<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}`)
}