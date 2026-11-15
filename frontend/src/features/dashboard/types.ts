import type { Role } from '../../types/auth'

export interface DeviationItem {
    item_name: string
    fail_count: number
    undetermined_count: number
}

export interface SupplierEditStat {
    supplier: string
    documents: number
    edited_documents: number
    edit_rate: number // 담당자가 값, 항목명을 고친 문서 / 처분 문서 (%)
    success_rate: number // 100 - edit_rate 
}

export interface ItemEditStat {
    item_name: string
    items: number
    edited_items: number
    edit_rate: number
}

export interface DashboardSummary {
    total_processed: number
    accept_count: number
    conditional_accept_count: number
    reject_count: number
    on_hold_count: number
    pass_rate: number
    avg_processing_time_sec: number
    recommendation_match_rate: number
    deviation_by_item: DeviationItem[]
    auto_approve_rate?: number
    reviewed_item_ratio?: number
    reason_code_counts?: Record<string, number>
    avg_system_processing_sec?: number | null
    avg_time_to_decision_sec?: number | null
    human_edit_rate?: number | null
    edit_rate_by_supplier?: SupplierEditStat[]
    edit_rate_by_item?: ItemEditStat[]
}

// scope는 보내지 않음. 서버가 USER는 본인(mine), ADMIN은 전체(all)로 정함.
export interface DashboardQuery {
    userId?: number
    materialCode?: string
    from?: string
    to?: string
}

// GET /users 응답 (ADMIN 전용)
export interface UserOption {
    id: number
    name: string
    role: Role
}