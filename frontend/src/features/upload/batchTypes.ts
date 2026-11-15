import type { DocumentStatus, LotRecommendation } from '../review/shared/api/types'
import type { DuplicateInfo } from './types'

// POST /documents/batch 응답 (명세 4.4-1)
export interface BatchAcceptedDocument {
    document_id: string
    file_name: string
    status: DocumentStatus
    receipt_id: string | null // 입고 CSV의 file_name으로 바로 연결된 입고 건
}

export interface BatchRejectedFile {
    file_name: string
    code: string // 예: INVALID_FILE, DUPLICATE_FILE
    message: string
    duplicates?: DuplicateInfo[] // DUPLICATE_FILE일 때 같은 파일의 기존 문서
    file?: File // 화면에서 붙여 두는 원본 파일("그래도 접수"로 다시 보낼 때 씀, 서버 응답엔 없음)
}

export interface BatchUploadResponse {
    batch_id: string
    documents: BatchAcceptedDocument[]
    rejected: BatchRejectedFile[] // 접수하지 않은 파일(형식·크기 오류). 나머지는 접수됨
    receipts: number // 입고 CSV 행 수
    linked_by_file: number // file_name으로 바로 연결된 문서 수
}

// 항목 판정 요약 (서버 schemas/extraction.py의 Summary. JSON에는 "pass"로 온다)
export interface ItemSummary {
    pass: number // 적합
    fail: number // 부적합
    undetermined: number // 판정 불가
    missing: number // 누락
    check: number // 확인 필요
}

// GET /documents/batch/{batch_id} 응답 (명세 4.4-2)
export interface BatchQueueItem {
    priority: number // 1 부적합, 2 서류 불일치, 3 판정 불가·누락·확인 필요, 4 정상, 5 처리 중, 0 격리
    priority_label: string
    document_id: string
    file_name: string
    supplier: string | null
    lot_no: string | null // CoA에서 읽은 로트번호
    received_lot_no: string | null // 입고 정보의 로트번호
    receipt_id: string | null
    spec_set_code: string | null
    status: DocumentStatus
    lot_recommendation: LotRecommendation | null
    document_issues: string[] // 문서 정합성 오류 코드 (예: LOT_MISMATCH)
    summary: ItemSummary | null
    error_message: string | null
}

export interface BatchSummary {
    total: number
    reject: number
    document_issue: number
    hold: number
    approve: number
    processing: number
    isolated: number
}

export interface UnmatchedReceipt {
    receipt_id: string
    supplier: string | null
    material_code: string
    received_lot_no: string
    spec_set_code: string | null
    received_date: string | null
    file_name: string | null
}

export interface BatchDetail {
    batch_id: string
    material_code: string
    created_by: string
    created_at: string
    summary: BatchSummary
    queue: BatchQueueItem[] // 검토 순서대로
    isolated: BatchQueueItem[] // 추출 실패 문서
    unmatched_receipts: UnmatchedReceipt[] // CoA가 연결되지 않은 입고 건
}