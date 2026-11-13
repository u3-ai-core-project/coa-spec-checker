export type DocumentStatus =
    | 'queued'
    | 'processing'
    | 'extracted'
    | 'in_review'
    | 'on_hold'
    | 'approved'
    | 'failed'

export type FinalDecision = 'accept' | 'conditional_accept' | 'reject'

// POST /documents 응답
export interface UploadResult {
    document_id: string
    file_name: string
    status: 'queued'
}

// GET /documents/{id} 응답 중 업로드 화면이 쓰는 필드
export interface DocumentDetail {
    document_id: string
    file_name: string
    supplier: string | null
    lot_no: string | null
    status: DocumentStatus
    final_decision: FinalDecision | null
    error_message: string | null
    failed_stage?: string | null
    error_kind?: 'permanent' | 'transient' | null
    attempt_count?: number
}