import { apiFetch } from '../../api/client'
import type { BatchDetail, BatchUploadResponse } from './batchTypes'

export interface CreateBatchParams {
    files: File[] // CoA 파일 1~20개 (PDF, PNG, JPG)
    receipts?: File // 입고 정보 CSV (선택)
    materialCode: string
    specSetCode?: string
    confirmDuplicate?: boolean // 같은 파일 경고를 보고 "그래도 접수"를 눌렀을 때
}

// 파일 여러 개와 입고 CSV를 한 번에 보냄.
// CSV와 CoA가 같은 요청 안에 있어야 서버가 서로 연결. 
export function createBatch({ files, receipts, materialCode, specSetCode, confirmDuplicate }: CreateBatchParams) {
    const form = new FormData()
    for (const file of files) form.append('files', file) // 같은 이름 'files'로 여러 번 붙인다
    form.append('material_code', materialCode)
    if (receipts) form.append('receipts', receipts)
    if (specSetCode) form.append('spec_set_code', specSetCode)
    if (confirmDuplicate) form.append('confirm_duplicate', 'true')
    return apiFetch<BatchUploadResponse>('/documents/batch', { method: 'POST', body: form })
}

// 배치 현황 (명세 4.4-2). 처리 중인 문서가 있으면 화면에서 주기적으로 다시 부른다
export function fetchBatch(batchId: string) {
    return apiFetch<BatchDetail>(`/documents/batch/${encodeURIComponent(batchId)}`)
}